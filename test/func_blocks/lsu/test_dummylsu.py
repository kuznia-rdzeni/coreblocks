import random
from collections import deque

from amaranth.sim import Settle, Passive

from transactron.lib import Adapter
from transactron.utils import int_to_signed, signed_to_int
from coreblocks.params import GenParams
from coreblocks.func_blocks.fu.lsu.dummyLsu import LSUDummy
from coreblocks.params.configurations import test_core_config
from coreblocks.frontend.decoder import *
from coreblocks.interface.keys import ExceptionReportKey, InstructionPrecommitKey
from transactron.utils.dependencies import DependencyManager
from coreblocks.interface.layouts import ExceptionRegisterLayouts, RetirementLayouts
from coreblocks.peripherals.wishbone import *
from transactron.testing import TestbenchIO, TestCaseWithSimulator, def_method_mock
from coreblocks.peripherals.bus_adapter import WishboneMasterAdapter
from test.peripherals.test_wishbone import WishboneInterfaceWrapper


def generate_aligned_addr(max_reg_val: int) -> int:
    return random.randint(0, max_reg_val // 4) * 4


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


def check_align(addr: int, op: tuple[OpType, Funct3]) -> bool:
    rest = addr % 4
    if op[1] in {Funct3.B, Funct3.BU}:
        return True
    if op[1] in {Funct3.H, Funct3.HU} and rest in {0, 2}:
        return True
    if op[1] == Funct3.W and rest == 0:
        return True
    return False


class DummyLSUTestCircuit(Elaboratable):
    def __init__(self, gen: GenParams):
        self.gen = gen

    def elaborate(self, platform):
        m = Module()

        wb_params = WishboneParameters(
            data_width=self.gen.isa.ilen,
            addr_width=32,
        )

        self.bus = WishboneMaster(wb_params)
        self.bus_master_adapter = WishboneMasterAdapter(self.bus)

        m.submodules.exception_report = self.exception_report = TestbenchIO(
            Adapter(i=self.gen.get(ExceptionRegisterLayouts).report)
        )

        self.gen.get(DependencyManager).add_dependency(ExceptionReportKey(), self.exception_report.adapter.iface)

        m.submodules.precommit = self.precommit = TestbenchIO(
            Adapter(o=self.gen.get(RetirementLayouts).precommit, nonexclusive=True)
        )
        self.gen.get(DependencyManager).add_dependency(InstructionPrecommitKey(), self.precommit.adapter.iface)

        m.submodules.func_unit = func_unit = LSUDummy(self.gen, self.bus_master_adapter)

        m.submodules.issue_mock = self.issue = TestbenchIO(AdapterTrans(func_unit.issue))
        m.submodules.accept_mock = self.accept = TestbenchIO(AdapterTrans(func_unit.accept))
        self.io_in = WishboneInterfaceWrapper(self.bus.wb_master)
        m.submodules.bus_master_adapter = self.bus_master_adapter
        m.submodules.bus = self.bus
        return m


class TestDummyLSULoads(TestCaseWithSimulator):
    def generate_instr(self, max_reg_val, max_imm_val):
        ops = {
            "LB": (OpType.LOAD, Funct3.B),
            "LBU": (OpType.LOAD, Funct3.BU),
            "LH": (OpType.LOAD, Funct3.H),
            "LHU": (OpType.LOAD, Funct3.HU),
            "LW": (OpType.LOAD, Funct3.W),
        }
        for i in range(self.tests_number):
            misaligned = False
            bus_err = random.random() < 0.1

            # generate new instructions till we generate correct one
            while True:
                # generate opcode
                (op, mask, signess) = generate_random_op(ops)
                # generate rp1, val1 which create addr
                s1_val = generate_aligned_addr(max_reg_val)
                imm = generate_imm(max_imm_val)
                addr = s1_val + imm

                if check_align(addr, op):
                    break

                if random.random() < 0.1:
                    misaligned = True
                    break

            exec_fn = {"op_type": op[0], "funct3": op[1], "funct7": 0}

            # calculate word address and mask
            mask = shift_mask_based_on_addr(mask, addr)
            word_addr = addr >> 2

            rp_dst = random.randint(0, 2**self.gen_params.phys_regs_bits - 1)
            rob_id = random.randint(0, 2**self.gen_params.rob_entries_bits - 1)
            instr = {
                "rp_dst": rp_dst,
                "rob_id": rob_id,
                "exec_fn": exec_fn,
                "s1_val": s1_val,
                "s2_val": 0,
                "imm": imm,
                "pc": 0,
            }
            self.instr_queue.appendleft(instr)
            self.mem_data_queue.appendleft(
                {
                    "addr": word_addr,
                    "mask": mask,
                    "sign": signess,
                    "rnd_bytes": bytes.fromhex(f"{random.randint(0,2**32-1):08x}"),
                    "misaligned": misaligned,
                    "err": bus_err,
                }
            )

            if misaligned or bus_err:
                self.exception_queue.appendleft(
                    {
                        "rob_id": rob_id,
                        "cause": (
                            ExceptionCause.LOAD_ADDRESS_MISALIGNED if misaligned else ExceptionCause.LOAD_ACCESS_FAULT
                        ),
                        "pc": 0,
                    }
                )

            self.exception_result.appendleft(
                misaligned or bus_err,
            )

    def setup_method(self) -> None:
        random.seed(14)
        self.tests_number = 100
        self.gen_params = GenParams(test_core_config.replace(phys_regs_bits=3, rob_entries_bits=3))
        self.test_module = DummyLSUTestCircuit(self.gen_params)
        self.instr_queue = deque()
        self.mem_data_queue = deque()
        self.returned_data = deque()
        self.exception_queue = deque()
        self.exception_result = deque()
        self.generate_instr(2**7, 2**7)
        self.max_wait = 10

    def wishbone_slave(self):
        yield Passive()

        while True:
            yield from self.test_module.io_in.slave_wait()
            generated_data = self.mem_data_queue.pop()

            if generated_data["misaligned"]:
                continue

            mask = generated_data["mask"]
            sign = generated_data["sign"]
            yield from self.test_module.io_in.slave_verify(generated_data["addr"], 0, 0, mask)
            yield from self.random_wait(self.max_wait)

            resp_data = int((generated_data["rnd_bytes"][:4]).hex(), 16)
            data_shift = (mask & -mask).bit_length() - 1
            assert mask.bit_length() == data_shift + mask.bit_count(), "Unexpected mask"

            size = mask.bit_count() * 8
            data_mask = 2**size - 1
            data = (resp_data >> (data_shift * 8)) & data_mask
            if sign:
                data = int_to_signed(signed_to_int(data, size), 32)
            if not generated_data["err"]:
                self.returned_data.appendleft(data)
            yield from self.test_module.io_in.slave_respond(resp_data, err=generated_data["err"])
            yield Settle()

    def inserter(self):
        for i in range(self.tests_number):
            req = self.instr_queue.pop()
            yield from self.test_module.issue.call(req)
            yield from self.random_wait(self.max_wait)

    def consumer(self):
        for i in range(self.tests_number):
            v = yield from self.test_module.accept.call()
            exc = self.exception_result.pop()
            if not exc:
                assert v["result"] == self.returned_data.pop()
            assert v["exception"] == exc

            yield from self.random_wait(self.max_wait)

    def test(self):
        @def_method_mock(lambda: self.test_module.exception_report)
        def exception_consumer(arg):
            assert arg == self.exception_queue.pop()

        with self.run_simulation(self.test_module) as sim:
            sim.add_sync_process(self.wishbone_slave)
            sim.add_sync_process(self.inserter)
            sim.add_sync_process(self.consumer)


class TestDummyLSULoadsCycles(TestCaseWithSimulator):
    def generate_instr(self, max_reg_val, max_imm_val):
        s1_val = random.randint(0, max_reg_val // 4) * 4
        imm = random.randint(0, max_imm_val // 4) * 4
        rp_dst = random.randint(0, 2**self.gen_params.phys_regs_bits - 1)
        rob_id = random.randint(0, 2**self.gen_params.rob_entries_bits - 1)

        exec_fn = {"op_type": OpType.LOAD, "funct3": Funct3.W, "funct7": 0}
        instr = {
            "rp_dst": rp_dst,
            "rob_id": rob_id,
            "exec_fn": exec_fn,
            "s1_val": s1_val,
            "s2_val": 0,
            "imm": imm,
            "pc": 0,
        }

        wish_data = {
            "addr": (s1_val + imm) >> 2,
            "mask": 0xF,
            "rnd_bytes": bytes.fromhex(f"{random.randint(0,2**32-1):08x}"),
        }
        return instr, wish_data

    def setup_method(self) -> None:
        random.seed(14)
        self.gen_params = GenParams(test_core_config.replace(phys_regs_bits=3, rob_entries_bits=3))
        self.test_module = DummyLSUTestCircuit(self.gen_params)

    def one_instr_test(self):
        instr, wish_data = self.generate_instr(2**7, 2**7)

        yield from self.test_module.issue.call(instr)
        yield from self.test_module.io_in.slave_wait()

        mask = wish_data["mask"]
        yield from self.test_module.io_in.slave_verify(wish_data["addr"], 0, 0, mask)
        data = wish_data["rnd_bytes"][:4]
        data = int(data.hex(), 16)
        yield from self.test_module.io_in.slave_respond(data)
        yield Settle()

        v = yield from self.test_module.accept.call()
        assert v["result"] == data

    def test(self):
        @def_method_mock(lambda: self.test_module.exception_report)
        def exception_consumer(arg):
            assert False

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
                # generate address
                s1_val = generate_aligned_addr(max_reg_val)
                imm = generate_imm(max_imm_val)
                addr = s1_val + imm
                if check_align(addr, op):
                    break

            data = s2_val = generate_aligned_addr(0xFFFFFFFF)

            exec_fn = {"op_type": op[0], "funct3": op[1], "funct7": 0}

            # calculate word address and mask
            mask = shift_mask_based_on_addr(mask, addr)
            addr = addr >> 2

            rob_id = random.randint(0, 2**self.gen_params.rob_entries_bits - 1)
            instr = {
                "rp_dst": 0,
                "rob_id": rob_id,
                "exec_fn": exec_fn,
                "s1_val": s1_val,
                "s2_val": s2_val,
                "imm": imm,
                "pc": 0,
            }
            self.instr_queue.appendleft(instr)
            self.mem_data_queue.appendleft({"addr": addr, "mask": mask, "data": bytes.fromhex(f"{data:08x}")})

    def setup_method(self) -> None:
        random.seed(14)
        self.tests_number = 100
        self.gen_params = GenParams(test_core_config.replace(phys_regs_bits=3, rob_entries_bits=3))
        self.test_module = DummyLSUTestCircuit(self.gen_params)
        self.instr_queue = deque()
        self.mem_data_queue = deque()
        self.get_result_data = deque()
        self.precommit_data = deque()
        self.generate_instr(2**7, 2**7)
        self.max_wait = 8

    def wishbone_slave(self):
        for i in range(self.tests_number):
            yield from self.test_module.io_in.slave_wait()
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
            yield from self.test_module.io_in.slave_verify(generated_data["addr"], data, 1, mask)
            yield from self.random_wait(self.max_wait)

            yield from self.test_module.io_in.slave_respond(0)
            yield Settle()

    def inserter(self):
        for i in range(self.tests_number):
            req = self.instr_queue.pop()
            self.get_result_data.appendleft(req["rob_id"])
            yield from self.test_module.issue.call(req)
            self.precommit_data.appendleft(req["rob_id"])
            yield from self.random_wait(self.max_wait)

    def get_resulter(self):
        for i in range(self.tests_number):
            v = yield from self.test_module.accept.call()
            rob_id = self.get_result_data.pop()
            assert v["rob_id"] == rob_id
            assert v["rp_dst"] == 0
            yield from self.random_wait(self.max_wait)
            self.precommit_data.pop()  # retire

    def precommiter(self):
        yield Passive()
        while True:
            while len(self.precommit_data) == 0:
                yield
            rob_id = self.precommit_data[-1]  # precommit is called continously until instruction is retired
            yield from self.test_module.precommit.call(rob_id=rob_id, side_fx=1)

    def test(self):
        @def_method_mock(lambda: self.test_module.exception_report)
        def exception_consumer(arg):
            assert False

        with self.run_simulation(self.test_module) as sim:
            sim.add_sync_process(self.wishbone_slave)
            sim.add_sync_process(self.inserter)
            sim.add_sync_process(self.get_resulter)
            sim.add_sync_process(self.precommiter)


class TestDummyLSUFence(TestCaseWithSimulator):
    def get_instr(self, exec_fn):
        return {"rp_dst": 1, "rob_id": 1, "exec_fn": exec_fn, "s1_val": 4, "s2_val": 1, "imm": 8, "pc": 0}

    def push_one_instr(self, instr):
        yield from self.test_module.issue.call(instr)

        if instr["exec_fn"]["op_type"] == OpType.LOAD:
            yield from self.test_module.io_in.slave_wait()
            yield from self.test_module.io_in.slave_respond(1)
            yield Settle()
        v = yield from self.test_module.accept.call()
        if instr["exec_fn"]["op_type"] == OpType.LOAD:
            assert v["result"] == 1

    def process(self):
        # just tests if FENCE doens't hang up the LSU
        load_fn = {"op_type": OpType.LOAD, "funct3": Funct3.W, "funct7": 0}
        fence_fn = {"op_type": OpType.FENCE, "funct3": 0, "funct7": 0}
        yield from self.push_one_instr(self.get_instr(load_fn))
        yield from self.push_one_instr(self.get_instr(fence_fn))
        yield from self.push_one_instr(self.get_instr(load_fn))

    def test_fence(self):
        self.gen_params = GenParams(test_core_config.replace(phys_regs_bits=3, rob_entries_bits=3))
        self.test_module = DummyLSUTestCircuit(self.gen_params)

        @def_method_mock(lambda: self.test_module.exception_report)
        def exception_consumer(arg):
            assert False

        with self.run_simulation(self.test_module) as sim:
            sim.add_sync_process(self.process)
