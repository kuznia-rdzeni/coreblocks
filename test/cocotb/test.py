from abc import ABC, abstractmethod
from collections.abc import Callable, Coroutine
from enum import Enum, auto
from typing import Any, Optional, TypeVar
import cocotb
import os
from glob import glob
from cocotb.utils import get_sim_time
from cocotb.clock import Clock, Timer
from cocotb.regression import TestFactory
from cocotb.handle import ModifiableObject
from cocotb.triggers import FallingEdge, RisingEdge, with_timeout
from cocotb.queue import Queue
from cocotb_bus.bus import Bus
from dataclasses import dataclass, replace
from elftools.elf.constants import P_FLAGS
from elftools.elf.elffile import ELFFile


@dataclass
class WishboneMasterSignals:
    adr: Any = 0
    we: Any = 0
    sel: Any = 0
    dat_w: Any = 0


@dataclass
class WishboneSlaveSignals:
    dat_r: Any = 0
    ack: Any = 0
    err: Any = 0
    rty: Any = 0


class WishboneBus(Bus):
    _signals = ["cyc", "stb", "we", "adr", "dat_r", "dat_w", "ack"]
    _optional_signals = ["sel", "err", "rty"]

    cyc: ModifiableObject
    stb: ModifiableObject
    we: ModifiableObject
    adr: ModifiableObject
    dat_r: ModifiableObject
    dat_w: ModifiableObject
    ack: ModifiableObject
    sel: ModifiableObject
    err: ModifiableObject
    rty: ModifiableObject

    def __init__(self, entity, name):
        super().__init__(entity, name, self._signals, self._optional_signals, bus_separator="__")


class ReplyStatus(Enum):
    OK = auto()
    ERROR = auto()
    RETRY = auto()


@dataclass
class ReadRequest:
    addr: int
    byte_count: int
    byte_sel: int


@dataclass
class ReadReply:
    data: int = 0
    status: ReplyStatus = ReplyStatus.OK


@dataclass
class WriteRequest:
    addr: int
    data: int
    byte_count: int
    byte_sel: int


@dataclass
class WriteReply:
    status: ReplyStatus = ReplyStatus.OK


class MemoryModel(ABC):
    @abstractmethod
    async def read(self, req: ReadRequest) -> ReadReply:
        raise NotImplementedError

    @abstractmethod
    async def write(self, req: WriteRequest) -> WriteReply:
        raise NotImplementedError


class RAMModel(MemoryModel):
    def __init__(self, clock, data: bytes, delay: int = 1):
        self.clock = clock
        self.delay = delay
        self.data = data

    async def read(self, req: ReadRequest) -> ReadReply:
        for _ in range(self.delay):
            await FallingEdge(self.clock)
        return ReadReply(data = int.from_bytes(self.data[req.addr : req.addr + req.byte_count], "little"))

    async def write(self, req: WriteRequest) -> WriteReply:
        raise NotImplementedError


class PutQueueModel(MemoryModel):
    def __init__(self, queue: Queue):
        self.queue = queue

    async def read(self, req: ReadRequest) -> ReadReply:
        raise RuntimeError("PutQueueModel read")

    async def write(self, req: WriteRequest) -> WriteReply:
        await self.queue.put(req)
        return WriteReply()


TReq = TypeVar("TReq", bound=ReadRequest | WriteRequest)
TRep = TypeVar("TRep", bound=ReadReply | WriteReply)


class CombinedModel(MemoryModel):
    def __init__(self, memory_ranges: list[tuple[range, MemoryModel]], fail_on_undefined=True):
        self.memory_ranges = memory_ranges
        self.fail_on_undefined = fail_on_undefined

    async def _run_on_range(self, f: Callable[[MemoryModel], Callable[[TReq], Coroutine[Any, Any, TRep]]], req: TReq) -> Optional[TRep]:
        for (address_range, model) in self.memory_ranges:
            if req.addr in address_range:
                return await f(model)(replace(req, addr=req.addr - address_range.start))

    async def read(self, req: ReadRequest) -> ReadReply:
        rep = await self._run_on_range(lambda m: m.read, req)
        if rep is not None:
            return rep
        if self.fail_on_undefined:
            raise RuntimeError("Undefined read: %x" % req.addr)
        else:
            return ReadReply(status=ReplyStatus.ERROR)

    async def write(self, req: WriteRequest) -> WriteReply:
        rep = await self._run_on_range(lambda m: m.write, req)
        if rep is not None:
            return rep
        if self.fail_on_undefined:
            raise RuntimeError("Undefined write: %x <= %x" % (req.addr, req.data))
        else:
            return WriteReply(status=ReplyStatus.ERROR)


class WishboneSlave:
    def __init__(self, entity, name: str, clock, model: MemoryModel, word_bits: int = 2):
        self.entity = entity
        self.name = name
        self.clock = clock
        self.model = model
        self.word_size = 2**word_bits
        self.word_bits = word_bits
        self.bus = WishboneBus(entity, name)
        self.bus.drive(WishboneSlaveSignals())

    async def start(self):
        clock_edge_event = FallingEdge(self.clock)

        while True:
            while not (self.bus.stb.value and self.bus.cyc.value):
                await clock_edge_event

            sig_m = WishboneMasterSignals()
            self.bus.sample(sig_m)
            print(sig_m)

            sig_s = WishboneSlaveSignals()
            if sig_m.we:
                resp = await self.model.write(
                    WriteRequest(addr=sig_m.adr << self.word_bits, data=sig_m.dat_w, byte_count=self.word_size, byte_sel=sig_m.sel)
                )
            else:
                resp = await self.model.read(ReadRequest(addr=sig_m.adr << self.word_bits, byte_count=self.word_size, byte_sel=sig_m.sel))
                sig_s.dat_r = resp.data

            match resp.status:
                case ReplyStatus.OK:
                    sig_s.ack = 1
                case ReplyStatus.ERROR:
                    if not self.bus.err:
                        raise ValueError("Bus doesn't support err")
                    sig_s.err = 1
                case ReplyStatus.RETRY:
                    if not self.bus.rty:
                        raise ValueError("Bus doesn't support rty")
                    sig_s.rty = 1

            print(sig_s)
            self.bus.drive(sig_s)
            await clock_edge_event
            self.bus.drive(WishboneSlaveSignals())


test_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
riscv_tests_dir = os.path.join(test_dir, "external", "riscv-tests")


async def test(dut, test_name):
    dut._log.setLevel(cocotb.logging.DEBUG)
    cocotb.logging.getLogger().setLevel(cocotb.logging.INFO)

    instr_segments: list[tuple[range, bytes]] = []
    data_segments: list[tuple[range, bytes]] = []

    file_name = os.path.join(riscv_tests_dir, "test-" + test_name)
    with open(file_name, "rb") as f:
        elffile = ELFFile(f)
        for segment in elffile.iter_segments():
            paddr = segment.header["p_paddr"]
            memsz = segment.header["p_memsz"]
            data = segment.data()
            data += bytes(memsz - len(data))
            segment_data = (range(paddr, paddr + memsz), segment.data())
            if segment.header["p_flags"] == P_FLAGS.PF_R | P_FLAGS.PF_X:
                instr_segments.append(segment_data)
            elif segment.header["p_flags"] == P_FLAGS.PF_R | P_FLAGS.PF_W:
                data_segments.append(segment_data)

    dut.rst.value = 1
    await Timer(1, "ns")
    dut.rst.value = 0

    clk = Clock(dut.clk, 1, "ns")
    cocotb.start_soon(clk.start())

    instr_mem = CombinedModel([(r, RAMModel(dut.clk, d)) for (r, d) in instr_segments])
    instr_wb = WishboneSlave(dut, "wb_instr", dut.clk, instr_mem)
    cocotb.start_soon(instr_wb.start())
#    print(dut.wb_instr__ack.value)
#    instr_wb.bus.drive(WishboneSlaveSignals(ack=1))
#    print(dut.wb_instr__ack.value)
#    await RisingEdge(dut.clk)
#    print(dut.wb_instr__ack.value)

    result_queue = Queue()
    data_models: list[tuple[range, MemoryModel]] = [(r, RAMModel(dut.clk, d)) for (r, d) in data_segments]
    data_models.append((range(0xFFFFFFF0, 0x100000000), PutQueueModel(result_queue)))
    data_mem = CombinedModel(data_models)
    data_wb = WishboneSlave(dut, "wb_data", dut.clk, data_mem)
    cocotb.start_soon(data_wb.start())

    req = await with_timeout(result_queue.get(), 5, "us")
    if req.data:
        raise RuntimeError("Failing test: %d" % req.data)

    sim_time = get_sim_time("ns")
    cocotb.logging.info(f"{test_name}: {sim_time}")


tf = TestFactory(test)
tf.add_option("test_name", [name[5:] for name in glob("test-*", root_dir=riscv_tests_dir)])
tf.generate_tests()
