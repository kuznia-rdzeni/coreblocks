import random
from collections import deque
from typing import Optional
from parameterized import parameterized_class
from dataclasses import dataclass, asdict

from amaranth.sim import Settle, Passive
from amaranth.hdl.rec import Direction

from coreblocks.params import OpType, GenParams
from coreblocks.lsu.dummyLsu import LSUDummy
from coreblocks.params.configurations import test_core_config
from coreblocks.params.isa import *
from coreblocks.peripherals.wishbone import *
from coreblocks.utils import ModuleConnector
from coreblocks.transactions.lib import Adapter
from coreblocks.utils._typing import LayoutLike
from test.common import *
from test.peripherals.test_wishbone import WishboneInterfaceWrapper
from test.message_framework import *


def compare_data_records(r1, r2) -> bool:
    return (r1["addr"] == r2["addr"]) and (r1["mask"] == r2["mask"])


def compare_data_records_loop(deq, n=3) -> bool:
    n = min(n + 1, len(deq))
    for i in range(1, n):
        for j in range(i + 1, n):
            if compare_data_records(deq[-i], deq[-j]):
                return True
    return False


def generate_register(max_reg_val: int, phys_regs_bits: int) -> tuple[int, int, Optional[dict[str, int]], int]:
    if random.randint(0, 1):
        rp = random.randint(1, 2**phys_regs_bits - 1)
        val = 0
        real_val = random.randint(0, max_reg_val // 4) * 4
        ann_data = {"tag": rp, "value": real_val}
    else:
        rp = 0
        val = random.randint(0, max_reg_val // 4) * 4
        real_val = val
        ann_data = None
    return rp, val, ann_data, real_val


def generate_random_op(ops: dict[str, tuple[OpType, Funct3]]) -> tuple[tuple[OpType, Funct3], int, bool]:
    ops_k = list(ops.keys())
    op = ops[ops_k[random.randint(0, len(ops) - 1)]]
    signess = False
    mask = 0xF
    if op[1] in {Funct3.B, Funct3.BU}:
        mask = 0x1
    if op[1] in {Funct3.H, Funct3.HU}:
        mask = 0x3
    if op[1] in {Funct3.B, Funct3.H}:
        signess = True
    return (op, mask, signess)


def generate_imm(max_imm_val: int) -> int:
    if random.randint(0, 1):
        return 0
    else:
        return random.randint(0, max_imm_val)


def shift_mask_based_on_addr(mask: int, addr: int) -> int:
    rest = addr % 4
    if mask == 0x1:
        mask = mask << rest
    elif mask == 0x3:
        mask = mask << rest
    return mask


def check_instr(addr: int, op: tuple[OpType, Funct3]) -> bool:
    rest = addr % 4
    if op[1] in {Funct3.B, Funct3.BU}:
        return True
    if op[1] in {Funct3.H, Funct3.HU} and rest in {0, 2}:
        return True
    if op[1] == Funct3.W and rest == 0:
        return True
    return False


def construct_test_module(gp):
    wb_params = WishboneParameters(data_width=gp.isa.ilen, addr_width=32)

    bus = WishboneMaster(wb_params)
    test_circuit = SimpleTestCircuit(LSUDummy(gp, bus))

    io_in = WishboneInterfaceWrapper(bus.wbMaster)
    return ModuleConnector(test_circuit=test_circuit, bus=bus), io_in


# ================================================================
# ================================================================
# ================================================================
# ================================================================
# ================================================================
# ================================================================


class WishboneMasterStub:
    def __init__(self, wb_params: WishboneParameters):
        # initialisation taken from peripherals/wishbone.py -- maybe there is possibility to make it common?
        self.wb_params = wb_params
        self.wb_layout = WishboneLayout(wb_params).wb_layout
        self.generate_layouts(wb_params)

        self.request_tb = TestbenchIO(Adapter(i=self.requestLayout))
        self.request = self.request_tb.adapter.iface
        self.result_tb = TestbenchIO(Adapter(o=self.resultLayout))
        self.result = self.result_tb.adapter.iface

    def generate_layouts(self, wb_params: WishboneParameters):
        # generate method layouts locally
        self.requestLayout: Any = [
            ("addr", wb_params.addr_width, DIR_FANIN),
            ("data", wb_params.data_width, DIR_FANIN),
            ("we", 1, DIR_FANIN),
            ("sel", wb_params.data_width // wb_params.granularity, DIR_FANIN),
        ]

        # TODO Fix typo Any to LayoutLike
        self.resultLayout: Any = [("data", wb_params.data_width), ("err", 1)]


def construct_test_module_new(gp) -> tuple[ModuleConnector, WishboneMasterStub]:
    wb_params = WishboneParameters(data_width=gp.isa.ilen, addr_width=32)

    bus = WishboneMasterStub(wb_params)
    test_circuit = SimpleTestCircuit(LSUDummy(gp, bus))

    return ModuleConnector(test_circuit=test_circuit, request_mock=bus.request_tb, result_mock=bus.result_tb), bus


@dataclass
class AnnounceData:
    tag: int
    value: int


@dataclass
class MemoryData:
    addr: int
    mask: int
    sign: bool
    rnd_bytes: bytes


@dataclass
class GeneratedData:
    ann_data: Optional[AnnounceData]
    instr: RecordIntDict
    mem_data: MemoryData


@parameterized_class(
    ("name", "max_wait", "max_reg_val", "max_imm_val"),
    [
        ("fast", 1, 2**7, 2**7),
        ("big_waits", 10, 2**7, 2**7),
    ],
)
class TestDummyLSULoadsNew(TestCaseWithMessageFramework):
    max_wait: int
    max_reg_val: int
    max_imm_val: int

    def setUp(self) -> None:
        # testing clear method in connection with wishbone slave mock is very tricky
        # and it is hard to cover all corner cases of test functionality
        # I suppose that there are still bugs in this test, but wuth occurence rate
        # less than 10^-4
        random.seed(14)
        self.tests_number = 100
        self.gp = GenParams(test_core_config.replace(phys_regs_bits=3, rob_entries_bits=3))
        self.test_module, self.bus = construct_test_module_new(self.gp)
        self.instr_queue = deque()
        self.announce_queue = deque()
        self.mem_data_queue = deque()
        self.returned_data = deque()
        self.cleared_queue_consumer = deque()
        self.cleared_queue_wb = deque()
        self.wishbone_request_valid = 0
        self.wishbone_data_from_last_req = None

    def generate_instr(self):
        ops = {
            "LB": (OpType.LOAD, Funct3.B),
            "LBU": (OpType.LOAD, Funct3.BU),
            "LH": (OpType.LOAD, Funct3.H),
            "LHU": (OpType.LOAD, Funct3.HU),
            "LW": (OpType.LOAD, Funct3.W),
        }

        # generate new instructions till we generate correct one
        while True:
            # generate opcode
            (op, mask, signess) = generate_random_op(ops)
            # generate rp1, val1 which create addr
            rp_s1, s1_val, ann_data, addr = generate_register(self.max_reg_val, self.gp.phys_regs_bits)
            imm = generate_imm(self.max_imm_val)
            addr += imm
            if check_instr(addr, op):
                break

        exec_fn = {"op_type": op[0], "funct3": op[1], "funct7": 0}

        # calculate word address and mask
        mask = shift_mask_based_on_addr(mask, addr)
        addr = addr >> 2

        rp_dst = random.randint(0, 2**self.gp.phys_regs_bits - 1)
        rob_id = random.randint(0, 2**self.gp.rob_entries_bits - 1)
        instr = {
            "rp_s1": rp_s1,
            "rp_s2": 0,
            "rp_dst": rp_dst,
            "rob_id": rob_id,
            "exec_fn": exec_fn,
            "s1_val": s1_val,
            "s2_val": 0,
            "imm": imm,
        }
        mem_data = MemoryData(
            **{
                "addr": addr,
                "mask": mask,
                "sign": signess,
                "rnd_bytes": bytes.fromhex(f"{random.randint(0,2**32-1):08x}"),
            }
        )
        ann_data = AnnounceData(**ann_data) if ann_data is not None else None
        return GeneratedData(ann_data, instr, mem_data)

    def clear_activator_filter(self, msg: InternalMessage):
        self.last_clear = msg.clk
        return False

    def cleared_filter(self, msg: InternalMessage):
        return msg.clk <= self.last_clear

    def test_body(self):
        with self.prepare_env(self.test_module):
            generator = MessageFrameworkProcess[Any, Any, GeneratedData](
                None, transformation_out=lambda x, y: self.generate_instr()
            )
            self.register_process("generator", generator)
            self.add_data_flow("starter", "generator")

            print(vars(self.test_module))
            print(vars(self.test_module.test_circuit))
            selector = MessageFrameworkProcess[RecordIntDict, RecordIntDict, Any](
                self.test_module.test_circuit.select,
                checker=lambda _, arg: self.assertEqual(arg["rs_entry_id"], 0),
                max_rand_wait=self.max_wait,
            )
            self.register_process("selector", selector)
            self.add_data_flow("starter", "selector")

            inserter = MessageFrameworkProcess[GeneratedData, GeneratedData, GeneratedData](
                self.test_module.test_circuit.insert,
                prepare_send_data=lambda req: {"rs_data": req.instr, "rs_entry_id": 0},
                transformation_out=lambda x, y: x,
                max_rand_wait=self.max_wait,
            )
            self.register_process("inserter", inserter)
            self.add_data_flow("generator", "inserter")

            def announce_transformation_in(arg: GeneratedData) -> AnnounceData:
                assert arg.ann_data is not None
                return arg.ann_data

            # this can not be lambda because we have to pass types explicte
            def announce_in_filter(arg: InternalMessage[GeneratedData]) -> bool:
                return arg.userdata.ann_data is None

            announcer = MessageFrameworkProcess[GeneratedData, AnnounceData, RecordIntDict](
                self.test_module.test_circuit.update,
                transformation_in=announce_transformation_in,
                prepare_send_data=lambda arg: asdict(arg),
                max_rand_wait=self.max_wait,
            )
            self.register_process("announcer", announcer)
            self.add_data_flow("inserter", "announcer", filter=announce_in_filter)

            cleaner = MessageFrameworkProcess(self.test_module.test_circuit.clear, max_rand_wait=self.max_wait)
            self.register_process("cleaner", cleaner)
            # TODO activate cleaner
            self.add_data_flow("starter", "cleaner", filter=lambda _: False)  # random.random()< 0.1)

            clear_filter_sink = MessageFrameworkProcess(None)
            self.register_process("clear_filter_sink", clear_filter_sink)
            self.add_data_flow("cleaner", "clear_filter_sink", filter=self.clear_activator_filter)

            self.wb_mock_acc = MessageFrameworkExternalAccess()
            self.register_accessor("wb_mock_acc", self.wb_mock_acc)
            self.add_data_flow("generator", "wb_mock_acc")

            consumer = MessageFrameworkProcess[GeneratedData, MemoryData, Any](
                self.test_module.test_circuit.get_result,
                transformation_in=lambda arg: arg.mem_data,
                checker=self.consumer_checker,
            )
            self.register_process("consumer", consumer)
            self.add_data_flow("inserter", "consumer")

            @def_method_mock(lambda: self.bus.request_tb, sched_prio=0)
            def request_mock(addr, data, we, sel):
                arg: GeneratedData = self.wb_mock_acc.get()

                self.assertEqual(addr, arg.mem_data.addr)
                self.assertEqual(we, 0)
                self.assertEqual(sel, arg.mem_data.mask)

                self.wishbone_request_valid = True
                self.wishbone_data_from_last_req = arg
                return

            @def_method_mock(lambda: self.bus.result_tb, enable=lambda: self.wishbone_request_valid, sched_prio=0)
            def response_mock(self):
                self.wishbone_request_valid = False
                data = self.wishbone_data_from_last_req["data"]
                return {"data": data, "err": 0}

    def consumer_checker(self, in_verif: MemoryData, arg: RecordIntDictRet):
        generated_data = int((in_verif.rnd_bytes[:4]).hex(), 16)
        data_shift = (in_verif.mask & -in_verif.mask).bit_length() - 1
        assert in_verif.mask.bit_length() == data_shift + in_verif.mask.bit_count(), "Unexpected mask"

        size = in_verif.mask.bit_count() * 8
        data_mask = 2**size - 1
        data = (generated_data >> (data_shift * 8)) & data_mask
        if in_verif.sign:
            data = int_to_signed(signed_to_int(data, size), 32)

        self.assertEqual(data, arg["result"])


# ================================================================
# ================================================================
# ================================================================
# ================================================================
# ================================================================
# ================================================================


@parameterized_class(
    ("name", "max_wait"),
    [
        ("fast", 1),
        ("big_waits", 10),
    ],
)
class TestDummyLSULoads(TestCaseWithSimulator):
    max_wait: int

    def generate_instr(self, max_reg_val, max_imm_val):
        ops = {
            "LB": (OpType.LOAD, Funct3.B),
            "LBU": (OpType.LOAD, Funct3.BU),
            "LH": (OpType.LOAD, Funct3.H),
            "LHU": (OpType.LOAD, Funct3.HU),
            "LW": (OpType.LOAD, Funct3.W),
        }
        for i in range(self.tests_number):
            # generate new instructions till we generate correct one
            while True:
                # generate opcode
                (op, mask, signess) = generate_random_op(ops)
                # generate rp1, val1 which create addr
                rp_s1, s1_val, ann_data, addr = generate_register(max_reg_val, self.gp.phys_regs_bits)
                imm = generate_imm(max_imm_val)
                addr += imm
                if check_instr(addr, op):
                    break

            self.announce_queue.append(ann_data)
            exec_fn = {"op_type": op[0], "funct3": op[1], "funct7": 0}

            # calculate word address and mask
            mask = shift_mask_based_on_addr(mask, addr)
            addr = addr >> 2

            rp_dst = random.randint(0, 2**self.gp.phys_regs_bits - 1)
            rob_id = random.randint(0, 2**self.gp.rob_entries_bits - 1)
            instr = {
                "rp_s1": rp_s1,
                "rp_s2": 0,
                "rp_dst": rp_dst,
                "rob_id": rob_id,
                "exec_fn": exec_fn,
                "s1_val": s1_val,
                "s2_val": 0,
                "imm": imm,
            }
            self.instr_queue.append(instr)
            self.mem_data_queue.append(
                {
                    "addr": addr,
                    "mask": mask,
                    "sign": signess,
                    "rnd_bytes": bytes.fromhex(f"{random.randint(0,2**32-1):08x}"),
                }
            )

    def setUp(self) -> None:
        # testing clear method in connection with wishbone slave mock is very tricky
        # and it is hard to cover all corner cases of test functionality
        # I suppose that there are still bugs in this test, but wuth occurence rate
        # less than 10^-4
        random.seed(14)
        self.tests_number = 100
        self.gp = GenParams(test_core_config.replace(phys_regs_bits=3, rob_entries_bits=3))
        self.test_module, self.io_in = construct_test_module(self.gp)
        self.instr_queue = deque()
        self.announce_queue = deque()
        self.mem_data_queue = deque()
        self.returned_data = deque()
        self.cleared_queue_consumer = deque()
        self.cleared_queue_wb = deque()
        self.generate_instr(2**7, 2**7)

    def random_wait(self):
        for i in range(random.randrange(self.max_wait)):
            yield

    def wishbone_slave(self):
        yield Passive()

        i = -1
        while True:
            i += 1
            yield from self.io_in.slave_wait()
            while self.cleared_queue_wb and self.cleared_queue_wb[0] < i:
                self.cleared_queue_wb.popleft()

            while self.cleared_queue_wb and self.cleared_queue_wb[0] == i:
                self.cleared_queue_wb.popleft()
                next_expected = self.mem_data_queue[-1]
                received_addr = yield self.io_in.wb.adr
                received_mask = yield self.io_in.wb.sel
                # check if clear was before request to wishbone, if yes omit this instruction
                if (next_expected["addr"] != received_addr) | (next_expected["mask"] != received_mask):
                    self.returned_data.append(-1)
                    self.mem_data_queue.pop()
                    i += 1
            generated_data = self.mem_data_queue.pop()

            mask = generated_data["mask"]
            sign = generated_data["sign"]
            yield from self.io_in.slave_verify(generated_data["addr"], 0, 0, mask)
            yield from self.random_wait()

            resp_data = int((generated_data["rnd_bytes"][:4]).hex(), 16)
            data_shift = (mask & -mask).bit_length() - 1
            assert mask.bit_length() == data_shift + mask.bit_count(), "Unexpected mask"

            size = mask.bit_count() * 8
            data_mask = 2**size - 1
            data = (resp_data >> (data_shift * 8)) & data_mask
            if sign:
                data = int_to_signed(signed_to_int(data, size), 32)
            self.returned_data.append(data)
            yield from self.io_in.slave_respond(resp_data)
            yield Settle()

    def inserter(self):
        for i in range(self.tests_number):
            req = self.instr_queue.pop()
            ret = yield from self.test_module.test_circuit.select.call()
            self.assertEqual(ret["rs_entry_id"], 0)
            yield from self.test_module.test_circuit.insert.call(rs_data=req, rs_entry_id=1)
            announc = self.announce_queue.pop()
            if announc is not None:
                yield from self.test_module.test_circuit.update.call(announc)
            yield from self.random_wait()
            if random.random() < 0.1:
                # to keep in sync inserter and wishbone slave mock i need to distinguish individual access
                # in clear conditions the only data which are available in wishobe is addr and sel.
                if (len(self.mem_data_queue) < 3) or compare_data_records_loop(self.mem_data_queue, n=4):
                    continue
                yield from self.test_module.test_circuit.clear.call()
                self.cleared_queue_consumer.append(i)
                self.cleared_queue_wb.append(i)
                yield from self.random_wait()

    def consumer(self):
        i = -1
        while i < self.tests_number:
            i += 1
            v = None
            while i < self.tests_number:
                v = yield from self.test_module.test_circuit.get_result.call_try()
                while self.cleared_queue_consumer and self.cleared_queue_consumer[0] < i:
                    self.cleared_queue_consumer.popleft()
                if self.cleared_queue_consumer and self.cleared_queue_consumer[0] == i and self.returned_data:
                    self.cleared_queue_consumer.popleft()
                    self.returned_data.popleft()
                    i += 1
                if v is not None:
                    break
            if i >= self.tests_number:
                break
            assert v is not None
            self.assertEqual(v["result"], self.returned_data.popleft())
            yield from self.random_wait()

    def test(self):
        with self.run_simulation(self.test_module) as sim:
            sim.add_sync_process(self.wishbone_slave)
            sim.add_sync_process(self.inserter)
            sim.add_sync_process(self.consumer)


class TestDummyLSULoadsCycles(TestCaseWithSimulator):
    def generate_instr(self, max_reg_val, max_imm_val):
        s1_val = random.randint(0, max_reg_val // 4) * 4
        imm = random.randint(0, max_imm_val // 4) * 4
        rp_dst = random.randint(0, 2**self.gp.phys_regs_bits - 1)
        rob_id = random.randint(0, 2**self.gp.rob_entries_bits - 1)

        exec_fn = {"op_type": OpType.LOAD, "funct3": Funct3.W, "funct7": 0}
        instr = {
            "rp_s1": 0,
            "rp_s2": 0,
            "rp_dst": rp_dst,
            "rob_id": rob_id,
            "exec_fn": exec_fn,
            "s1_val": s1_val,
            "s2_val": 0,
            "imm": imm,
        }

        wish_data = {
            "addr": (s1_val + imm) >> 2,
            "mask": 0xF,
            "rnd_bytes": bytes.fromhex(f"{random.randint(0,2**32-1):08x}"),
        }
        return instr, wish_data

    def setUp(self) -> None:
        random.seed(14)
        self.gp = GenParams(test_core_config.replace(phys_regs_bits=3, rob_entries_bits=3))
        self.test_module, self.io_in = construct_test_module(self.gp)

    def one_instr_test(self):
        instr, wish_data = self.generate_instr(2**7, 2**7)

        ret = yield from self.test_module.test_circuit.select.call()
        self.assertEqual(ret["rs_entry_id"], 0)
        yield from self.test_module.test_circuit.insert.call(rs_data=instr, rs_entry_id=1)
        yield from self.io_in.slave_wait()

        mask = wish_data["mask"]
        yield from self.io_in.slave_verify(wish_data["addr"], 0, 0, mask)
        data = wish_data["rnd_bytes"][:4]
        data = int(data.hex(), 16)
        yield from self.io_in.slave_respond(data)
        yield Settle()

        v = yield from self.test_module.test_circuit.get_result.call()
        self.assertEqual(v["result"], data)

    def test(self):
        with self.run_simulation(self.test_module) as sim:
            sim.add_sync_process(self.one_instr_test)


class TestDummyLSUStores(TestCaseWithSimulator):
    def generate_instr(self, max_reg_val, max_imm_val):
        ops = {
            "SB": (OpType.STORE, Funct3.B),
            "SH": (OpType.STORE, Funct3.H),
            "SW": (OpType.STORE, Funct3.W),
        }
        for i in range(self.tests_number):
            while True:
                # generate opcode
                (op, mask, _) = generate_random_op(ops)
                # generate rp1, val1 which create addr
                rp_s1, s1_val, ann_data1, addr = generate_register(max_reg_val, self.gp.phys_regs_bits)
                imm = generate_imm(max_imm_val)
                addr += imm
                if check_instr(addr, op):
                    break

            rp_s2, s2_val, ann_data2, data = generate_register(0xFFFFFFFF, self.gp.phys_regs_bits)
            if rp_s1 == rp_s2 and ann_data1 is not None and ann_data2 is not None:
                ann_data2 = None
                data = ann_data1["value"]
            # decide in which order we would get announcments
            if random.randint(0, 1):
                self.announce_queue.append((ann_data1, ann_data2))
            else:
                self.announce_queue.append((ann_data2, ann_data1))

            exec_fn = {"op_type": op[0], "funct3": op[1], "funct7": 0}

            # calculate word address and mask
            mask = shift_mask_based_on_addr(mask, addr)
            addr = addr >> 2

            rob_id = random.randint(0, 2**self.gp.rob_entries_bits - 1)
            instr = {
                "rp_s1": rp_s1,
                "rp_s2": rp_s2,
                "rp_dst": 0,
                "rob_id": rob_id,
                "exec_fn": exec_fn,
                "s1_val": s1_val,
                "s2_val": s2_val,
                "imm": imm,
            }
            self.instr_queue.append(instr)
            self.mem_data_queue.append({"addr": addr, "mask": mask, "data": bytes.fromhex(f"{data:08x}")})

    def setUp(self) -> None:
        random.seed(14)
        self.tests_number = 100
        self.gp = GenParams(test_core_config.replace(phys_regs_bits=3, rob_entries_bits=3))
        self.test_module, self.io_in = construct_test_module(self.gp)
        self.instr_queue = deque()
        self.announce_queue = deque()
        self.mem_data_queue = deque()
        self.get_result_data = deque()
        self.commit_data = deque()
        self.generate_instr(2**7, 2**7)

    def random_wait(self):
        for i in range(random.randint(0, 8)):
            yield

    def wishbone_slave(self):
        for i in range(self.tests_number):
            yield from self.io_in.slave_wait()
            generated_data = self.mem_data_queue.pop()

            mask = generated_data["mask"]
            b_dict = {1: 0, 2: 8, 4: 16, 8: 24}
            h_dict = {3: 0, 0xC: 16}
            if mask in b_dict:
                data = (int(generated_data["data"][-1:].hex(), 16) & 0xFF) << b_dict[mask]
            elif mask in h_dict:
                data = (int(generated_data["data"][-2:].hex(), 16) & 0xFFFF) << h_dict[mask]
            else:
                data = int(generated_data["data"][-4:].hex(), 16)
            yield from self.io_in.slave_verify(generated_data["addr"], data, 1, mask)
            yield from self.random_wait()

            yield from self.io_in.slave_respond(0)
            yield Settle()

    def inserter(self):
        for i in range(self.tests_number):
            req = self.instr_queue.pop()
            self.get_result_data.appendleft(req["rob_id"])
            ret = yield from self.test_module.test_circuit.select.call()
            self.assertEqual(ret["rs_entry_id"], 0)
            yield from self.test_module.test_circuit.insert.call(rs_data=req, rs_entry_id=0)
            announc = self.announce_queue.pop()
            for j in range(2):
                if announc[j] is not None:
                    yield from self.random_wait()
                    yield from self.test_module.test_circuit.update.call(announc[j])
            yield from self.random_wait()

    def get_resulter(self):
        for i in range(self.tests_number):
            v = yield from self.test_module.test_circuit.get_result.call()
            rob_id = self.get_result_data.pop()
            self.commit_data.appendleft(rob_id)
            self.assertEqual(v["rob_id"], rob_id)
            self.assertEqual(v["rp_dst"], 0)
            yield from self.random_wait()

    def commiter(self):
        for i in range(self.tests_number):
            while len(self.commit_data) == 0:
                yield
            rob_id = self.commit_data.pop()
            yield from self.test_module.test_circuit.commit.call(rob_id=rob_id)

    def test(self):
        with self.run_simulation(self.test_module) as sim:
            sim.add_sync_process(self.wishbone_slave)
            sim.add_sync_process(self.inserter)
            sim.add_sync_process(self.get_resulter)
            sim.add_sync_process(self.commiter)
