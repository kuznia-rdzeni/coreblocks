from abc import ABC, abstractmethod
from enum import Enum, auto
from typing import Any
import cocotb
from cocotb.utils import get_sim_time
from cocotb.clock import Clock, Timer
from cocotb.regression import TestFactory
from cocotb.handle import ModifiableObject
from cocotb.triggers import RisingEdge, with_timeout
from cocotb.queue import Queue
from cocotb_bus.bus import Bus
from dataclasses import dataclass


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
    byte_sel: int


@dataclass
class ReadReply:
    data: int = 0
    status: ReplyStatus = ReplyStatus.OK


@dataclass
class WriteRequest:
    addr: int
    data: int
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
    def __init__(self, clock, delay=1):
        self.clock = clock
        self.delay = delay

    async def read(self, req: ReadRequest) -> ReadReply:
        raise NotImplementedError
    
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


class CombinedModel(MemoryModel):
    def __init__(self, memory_ranges: list[tuple[range, MemoryModel]], fail_on_undefined=True):
        self.memory_ranges = memory_ranges
        self.fail_on_undefined = fail_on_undefined

    async def read(self, req: ReadRequest) -> ReadReply:
        for (address_range, model) in self.memory_ranges:
            if req.addr in address_range:
                return await model.read(req)
        if self.fail_on_undefined:
            raise RuntimeError("Undefined read: %x" % req.addr)
        else:
            return ReadReply(status=ReplyStatus.ERROR)
    
    async def write(self, req: WriteRequest) -> WriteReply:
        for (address_range, model) in self.memory_ranges:
            if req.addr in address_range:
                return await model.write(req)
        if self.fail_on_undefined:
            raise RuntimeError("Undefined write: %x <= %x" % (req.addr, req.data))
        else:
            return WriteReply(status=ReplyStatus.ERROR)


class WishboneSlave:
    def __init__(self, entity, name, clock, model: MemoryModel):
        self.entity = entity
        self.name = name
        self.clock = clock
        self.model = model
        self.bus = WishboneBus(entity, name)

    async def start(self):
        clock_edge_event = RisingEdge(self.clock)

        while True:
            while not (self.bus.stb.value and self.bus.cyc.value):
                await clock_edge_event

            sig_m = WishboneMasterSignals()
            self.bus.sample(sig_m)

            sig_s = WishboneSlaveSignals()
            if sig_m.we:
                resp = await self.model.write(WriteRequest(addr=sig_m.adr, data=sig_m.dat_w, byte_sel=sig_m.sel))
            else:
                resp = await self.model.read(ReadRequest(addr=sig_m.adr, byte_sel=sig_m.sel))
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

            self.bus.drive(sig_s)


async def test(dut, test_name):
    cocotb.logging.getLogger().setLevel(cocotb.logging.INFO)

    dut.rst.value = 1
    await Timer(1, 'ns')

    clk = Clock(dut.clk, 1, 'ns')
    await cocotb.start(clk.start())

    instr_mem = CombinedModel([])
    instr_wb = WishboneSlave(dut, "wb_instr", dut.clk, instr_mem)
    instr_task = await cocotb.start(instr_wb.start())

    result_queue = Queue()
    data_mem = CombinedModel([(range(0xfffffff0, 0x100000000), PutQueueModel(result_queue))])
    data_wb = WishboneSlave(dut, "wb_data", dut.clk, data_mem)
    data_task = await cocotb.start(data_wb.start())

    req = await with_timeout(result_queue.get(), 5, 'us')
    if req.data:
        raise RuntimeError("Failing test: %d" % req.data)

    sim_time = get_sim_time('ns')
    cocotb.logging.info(f"{test_name}: {sim_time}")


tf = TestFactory(test)
tf.add_option("test_name", ["add", "addi"])
tf.generate_tests()
