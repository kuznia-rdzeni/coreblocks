from collections import deque
import random
import pytest

from coreblocks.params import GenParams
from coreblocks.arch import Funct3, Funct7
from coreblocks.arch import OpType
from coreblocks.params.configurations import test_core_config
from coreblocks.scheduler.scheduler import RSSelection
from transactron.testing import SimpleTestCircuit, TestCaseWithSimulator, TestbenchIO, TestbenchContext
from transactron.testing.functions import data_const_to_dict
from transactron.testing.method_mock import MethodMock, def_method_mock
from .test_scheduler import MockedBlockComponent

_rs1_optypes = {OpType.ARITHMETIC, OpType.COMPARE}
_rs2_optypes = {OpType.LOGIC, OpType.COMPARE}


class TestRSSelect(TestCaseWithSimulator):
    @pytest.fixture(autouse=True)
    def setup_method(self):
        self.gen_params = GenParams(
            test_core_config.replace(
                func_units_config=(MockedBlockComponent(_rs1_optypes, 4), MockedBlockComponent(_rs2_optypes, 4)),
                allow_partial_extensions=True,
            )
        )
        self.m = SimpleTestCircuit(RSSelection(gen_params=self.gen_params))
        self.expected_out: deque[dict] = deque()
        self.input_instrs: deque[dict] = deque()
        self.instr_in: deque[dict] = deque()
        random.seed(1789)

    def gen_instrs(self, instr_count: int, optypes: set[OpType]):
        for i in range(instr_count):
            rp_dst = random.randrange(self.gen_params.phys_regs_bits)
            rp_s1 = random.randrange(self.gen_params.phys_regs_bits)
            rp_s2 = random.randrange(self.gen_params.phys_regs_bits)

            op_type = random.choice(list(optypes))
            funct3 = random.choice(list(Funct3))
            funct7 = random.choice(list(Funct7))

            immediate = random.randrange(2**32)

            rob_id = random.randrange(self.gen_params.rob_entries_bits)
            pc = random.randrange(2**32)
            csr = random.randrange(2**self.gen_params.isa.csr_alen)

            instr = {
                "exec_fn": {
                    "op_type": op_type,
                    "funct3": funct3,
                    "funct7": funct7,
                },
                "regs_p": {
                    "rp_dst": rp_dst,
                    "rp_s1": rp_s1,
                    "rp_s2": rp_s2,
                },
                "rob_id": rob_id,
                "imm": immediate,
                "csr": csr,
                "pc": pc,
                "tag": 0,
            }

            self.input_instrs.append(instr)

    def create_instr_input_process(self, enable_prob: float = 1.0):
        @def_method_mock(lambda: self.m.get_instrs, enable=lambda: random.random() <= enable_prob)
        def process(count: int):
            @MethodMock.effect
            def eff():
                for _ in range(count):
                    self.instr_in.append(self.input_instrs.popleft())

            return {"count": count, "data": [self.input_instrs[0]]}

        return process()

    def create_rs_alloc_process(self, io: TestbenchIO, rs_id: int, rs_optypes: set[OpType], enable_prob: float = 1):
        @def_method_mock(lambda: io, enable=lambda: random.random() <= enable_prob, delay=1e-9)
        def process():
            random_entry = random.randrange(self.gen_params.max_rs_entries)

            @MethodMock.effect
            def eff():
                expected = self.instr_in.popleft()
                assert expected["exec_fn"]["op_type"] in rs_optypes
                expected["rs_entry_id"] = random_entry
                expected["rs_selected"] = rs_id
                self.expected_out.append(expected)

            return {"rs_entry_id": random_entry}

        return process()

    @def_method_mock(lambda self: self.m.peek_instrs, enable=lambda self: bool(self.input_instrs))
    def peek_instrs_mock(self):
        return {"count": 1, "data": [self.input_instrs[0]]}

    @def_method_mock(lambda self: self.m.rf_read_req[0])
    def rf_read_req1_mock(self, reg_id):
        pass

    @def_method_mock(lambda self: self.m.rf_read_req[1])
    def rf_read_req2_mock(self, reg_id):
        pass

    def create_output_process(self, instr_count: int, random_wait: int = 0):
        async def process(sim: TestbenchContext):
            for _ in range(instr_count):
                result = await self.m.push_instrs.call(sim)
                if result.count == 0:
                    continue

                outputs = self.expected_out.popleft()

                await self.random_wait(sim, random_wait)
                assert result.count == 1
                assert data_const_to_dict(result.data[0]) == outputs

        return process

    def test_base_functionality(self):
        """
        Test checking basic functionality when both RS select methods are available.
        """

        self.gen_instrs(100, _rs1_optypes.union(_rs2_optypes))
        with self.run_simulation(self.m, max_cycles=1500) as sim:
            self.add_mock(sim, self.create_instr_input_process())
            self.add_mock(sim, self.create_rs_alloc_process(self.m.rs_select[0], rs_id=0, rs_optypes=_rs1_optypes))
            self.add_mock(sim, self.create_rs_alloc_process(self.m.rs_select[1], rs_id=1, rs_optypes=_rs2_optypes))
            sim.add_testbench(self.create_output_process(100))

    def test_only_rs1(self):
        """
        Test checking if instruction will get allocated if first the RS is full and
        the RS select method is not available.
        """

        self.gen_instrs(100, _rs1_optypes.intersection(_rs2_optypes))
        with self.run_simulation(self.m, max_cycles=1500) as sim:
            self.add_mock(sim, self.create_instr_input_process())
            self.add_mock(sim, self.create_rs_alloc_process(self.m.rs_select[0], rs_id=0, rs_optypes=_rs1_optypes))
            sim.add_testbench(self.create_output_process(100))

    def test_only_rs2(self):
        """
        Test checking if an instruction will get allocated if the second RS is full and
        the RS select method is not available.
        """

        self.gen_instrs(100, _rs1_optypes.intersection(_rs2_optypes))
        with self.run_simulation(self.m, max_cycles=1500) as sim:
            self.add_mock(sim, self.create_instr_input_process())
            self.add_mock(sim, self.create_rs_alloc_process(self.m.rs_select[1], rs_id=1, rs_optypes=_rs2_optypes))
            sim.add_testbench(self.create_output_process(100))

    def test_delays(self):
        """
        Test checking if instructions get allocated correctly if there are delays
        in methods availability.
        """

        self.gen_instrs(300, _rs1_optypes.union(_rs2_optypes))
        with self.run_simulation(self.m, max_cycles=5000) as sim:
            self.add_mock(sim, self.create_instr_input_process(enable_prob=0.3))
            self.add_mock(
                sim,
                self.create_rs_alloc_process(self.m.rs_select[0], rs_id=0, rs_optypes=_rs1_optypes, enable_prob=0.1),
            )
            self.add_mock(
                sim,
                self.create_rs_alloc_process(self.m.rs_select[1], rs_id=1, rs_optypes=_rs2_optypes, enable_prob=0.1),
            )
            sim.add_testbench(self.create_output_process(300, random_wait=12))
