import random
from collections import deque
from amaranth import *

from transactron.lib import Adapter, AdapterTrans
from transactron.utils import int_to_signed, signed_to_int
from transactron.utils.dependencies import DependencyContext
from transactron.testing.method_mock import MethodMock
from transactron.testing import CallTrigger, TestbenchIO, TestCaseWithSimulator, def_method_mock, TestbenchContext
from coreblocks.params import GenParams
from coreblocks.func_blocks.fu.lsu.dummyLsu import LSUDummy
from coreblocks.params.configurations import test_core_config
from coreblocks.arch import *
from coreblocks.interface.keys import CoreStateKey, ExceptionReportKey, InstructionPrecommitKey
from coreblocks.interface.layouts import ExceptionRegisterLayouts, RetirementLayouts
from ...peripherals.bus_mock import BusMockParameters, MockMasterAdapter


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

        bus_mock_params = BusMockParameters(data_width=self.gen.isa.ilen, addr_width=32)

        self.bus_master_adapter = MockMasterAdapter(bus_mock_params)

        m.submodules.exception_report = self.exception_report = TestbenchIO(
            Adapter.create(i=self.gen.get(ExceptionRegisterLayouts).report)
        )

        DependencyContext.get().add_dependency(ExceptionReportKey(), self.exception_report.adapter.iface)

        layouts = self.gen.get(RetirementLayouts)
        m.submodules.precommit = self.precommit = TestbenchIO(
            Adapter.create(
                i=layouts.precommit_in,
                o=layouts.precommit_out,
                nonexclusive=True,
                combiner=lambda m, args, runs: args[0],
            ).set(with_validate_arguments=True)
        )
        DependencyContext.get().add_dependency(InstructionPrecommitKey(), self.precommit.adapter.iface)

        m.submodules.core_state = self.core_state = TestbenchIO(Adapter.create(o=layouts.core_state, nonexclusive=True))
        DependencyContext.get().add_dependency(CoreStateKey(), self.core_state.adapter.iface)

        m.submodules.func_unit = func_unit = LSUDummy(self.gen, self.bus_master_adapter)

        m.submodules.issue_mock = self.issue = TestbenchIO(AdapterTrans(func_unit.issue))
        m.submodules.accept_mock = self.accept = TestbenchIO(AdapterTrans(func_unit.accept))
        m.submodules.bus_master_adapter = self.bus_master_adapter
        return m


class TestDummyLSULoads(TestCaseWithSimulator):
    last_rob_id: int = 0

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
            self.last_rob_id = (self.last_rob_id + 1) % 2**self.gen_params.rob_entries_bits
            rob_id = self.last_rob_id
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
                    "rnd_bytes": bytes.fromhex(f"{random.randint(0, 2**32-1):08x}"),
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
                        "mtval": addr,
                    }
                )

            self.exception_result.append(
                {"rob_id": rob_id, "err": misaligned or bus_err},
            )

    def setup_method(self) -> None:
        random.seed(14)
        self.tests_number = 100
        self.gen_params = GenParams(test_core_config.replace(phys_regs_bits=3, rob_entries_bits=4))
        self.test_module = DummyLSUTestCircuit(self.gen_params)
        self.instr_queue = deque()
        self.mem_data_queue = deque()
        self.returned_data = deque()
        self.exception_queue = deque()
        self.exception_result = deque()
        self.free_rob_id = set(range(2**self.gen_params.rob_entries_bits))
        self.generate_instr(2**7, 2**7)
        self.max_wait = 10

    async def bus_mock(self, sim: TestbenchContext):
        while self.mem_data_queue:
            generated_data = self.mem_data_queue.pop()

            if generated_data["misaligned"]:
                continue

            mask = generated_data["mask"]
            sign = generated_data["sign"]
            req = await self.test_module.bus_master_adapter.request_read_mock.call(sim)
            assert req.addr == generated_data["addr"]
            assert req.sel == mask
            await self.random_wait(sim, self.max_wait)

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
            await self.test_module.bus_master_adapter.get_read_response_mock.call(
                sim, data=resp_data, err=generated_data["err"]
            )

    async def inserter(self, sim: TestbenchContext):
        for i in range(self.tests_number):
            req = self.instr_queue.pop()
            while req["rob_id"] not in self.free_rob_id:
                await sim.tick()
            self.free_rob_id.remove(req["rob_id"])
            await self.test_module.issue.call(sim, req)
            await self.random_wait(sim, self.max_wait)

    async def consumer(self, sim: TestbenchContext):
        for i in range(self.tests_number):
            v = await self.test_module.accept.call(sim)
            rob_id = v["rob_id"]
            assert rob_id not in self.free_rob_id
            self.free_rob_id.add(rob_id)

            exc = next(i for i in self.exception_result if i["rob_id"] == rob_id)
            self.exception_result.remove(exc)
            if not exc["err"]:
                assert v["result"] == self.returned_data.pop()
            assert v["exception"] == exc["err"]

            await self.random_wait(sim, self.max_wait)

    def test(self):
        @def_method_mock(lambda: self.test_module.exception_report)
        def exception_consumer(arg):
            @MethodMock.effect
            def eff():
                assert arg == self.exception_queue.pop()

        @def_method_mock(lambda: self.test_module.precommit, validate_arguments=lambda rob_id: True)
        def precommiter(rob_id):
            return {"side_fx": 1}

        @def_method_mock(lambda: self.test_module.core_state)
        def core_state_process():
            return {"flushing": 0}

        with self.run_simulation(self.test_module) as sim:
            sim.add_testbench(self.bus_mock, background=True)
            sim.add_testbench(self.inserter)
            sim.add_testbench(self.consumer)


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

        data = {
            "addr": (s1_val + imm) >> 2,
            "mask": 0xF,
            "rnd_bytes": bytes.fromhex(f"{random.randint(0, 2**32-1):08x}"),
        }
        return instr, data

    def setup_method(self) -> None:
        random.seed(14)
        self.gen_params = GenParams(test_core_config.replace(phys_regs_bits=3, rob_entries_bits=3))
        self.test_module = DummyLSUTestCircuit(self.gen_params)

    async def one_instr_test(self, sim: TestbenchContext):
        instr, data = self.generate_instr(2**7, 2**7)

        await self.test_module.issue.call(sim, instr)

        mask = data["mask"]
        req = await self.test_module.bus_master_adapter.request_read_mock.call(sim)
        assert req.addr == data["addr"]
        assert req.sel == mask
        data = data["rnd_bytes"][:4]
        data = int(data.hex(), 16)
        r, v = (
            await CallTrigger(sim)
            .call(self.test_module.bus_master_adapter.get_read_response_mock, data=data, err=0)
            .call(self.test_module.accept)
        )
        assert r is not None and v is not None
        assert v["result"] == data

    def test(self):
        @def_method_mock(lambda: self.test_module.exception_report)
        def exception_consumer(arg):
            @MethodMock.effect
            def eff():
                assert False

        @def_method_mock(lambda: self.test_module.precommit, validate_arguments=lambda rob_id: True)
        def precommiter(rob_id):
            return {"side_fx": 1}

        with self.run_simulation(self.test_module) as sim:
            sim.add_testbench(self.one_instr_test)


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

    async def bus_mock(self, sim: TestbenchContext):
        for i in range(self.tests_number):
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
            req = await self.test_module.bus_master_adapter.request_write_mock.call(sim)
            assert req.addr == generated_data["addr"]
            assert req.data == data
            assert req.sel == generated_data["mask"]
            await self.random_wait(sim, self.max_wait)

            await self.test_module.bus_master_adapter.get_write_response_mock.call(sim, err=0)

    async def inserter(self, sim: TestbenchContext):
        for i in range(self.tests_number):
            req = self.instr_queue.pop()
            self.get_result_data.appendleft(req["rob_id"])
            await self.test_module.issue.call(sim, req)
            self.precommit_data.appendleft(req["rob_id"])
            await self.random_wait(sim, self.max_wait)

    async def get_resulter(self, sim: TestbenchContext):
        for i in range(self.tests_number):
            v = await self.test_module.accept.call(sim)
            rob_id = self.get_result_data.pop()
            assert v["rob_id"] == rob_id
            assert v["rp_dst"] == 0
            await self.random_wait(sim, self.max_wait)
            self.precommit_data.pop()  # retire

    def precommit_validate(self, rob_id):
        return len(self.precommit_data) > 0 and rob_id == self.precommit_data[-1]

    @def_method_mock(lambda self: self.test_module.precommit, validate_arguments=precommit_validate)
    def precommiter(self, rob_id):
        return {"side_fx": 1}

    def test(self):
        @def_method_mock(lambda: self.test_module.exception_report)
        def exception_consumer(arg):
            @MethodMock.effect
            def eff():
                assert False

        with self.run_simulation(self.test_module) as sim:
            sim.add_testbench(self.bus_mock)
            sim.add_testbench(self.inserter)
            sim.add_testbench(self.get_resulter)


class TestDummyLSUFence(TestCaseWithSimulator):
    def get_instr(self, exec_fn):
        return {"rp_dst": 1, "rob_id": 1, "exec_fn": exec_fn, "s1_val": 4, "s2_val": 1, "imm": 8, "pc": 0}

    async def push_one_instr(self, sim: TestbenchContext, instr):
        await self.test_module.issue.call(sim, instr)

        v = await self.test_module.accept.call(sim)
        if instr["exec_fn"]["op_type"] == OpType.LOAD:
            assert v.result == 1

    async def process(self, sim: TestbenchContext):
        # just tests if FENCE doens't hang up the LSU
        load_fn = {"op_type": OpType.LOAD, "funct3": Funct3.W, "funct7": 0}
        fence_fn = {"op_type": OpType.FENCE, "funct3": 0, "funct7": 0}
        await self.push_one_instr(sim, self.get_instr(load_fn))
        await self.push_one_instr(sim, self.get_instr(fence_fn))
        await self.push_one_instr(sim, self.get_instr(load_fn))

    def test_fence(self):
        self.gen_params = GenParams(test_core_config.replace(phys_regs_bits=3, rob_entries_bits=3))
        self.test_module = DummyLSUTestCircuit(self.gen_params)

        @def_method_mock(lambda: self.test_module.exception_report)
        def exception_consumer(arg):
            @MethodMock.effect
            def eff():
                assert False

        @def_method_mock(lambda: self.test_module.precommit, validate_arguments=lambda rob_id: True)
        def precommiter(rob_id):
            return {"side_fx": 1}

        pending_req = False

        @def_method_mock(lambda: self.test_module.bus_master_adapter.request_read_mock, enable=lambda: not pending_req)
        def request_read(addr, sel):
            @MethodMock.effect
            def eff():
                nonlocal pending_req
                pending_req = True

        @def_method_mock(lambda: self.test_module.bus_master_adapter.get_read_response_mock, enable=lambda: pending_req)
        def read_response():
            @MethodMock.effect
            def eff():
                nonlocal pending_req
                pending_req = False

            return {"data": 1, "err": 0}

        with self.run_simulation(self.test_module) as sim:
            sim.add_testbench(self.process)
