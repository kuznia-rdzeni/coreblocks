from collections import deque
import random

from amaranth import *

from coreblocks.params import GenParams
from coreblocks.interface.layouts import RFLayouts, RSLayouts, SchedulerLayouts
from coreblocks.arch import Funct3, Funct7
from coreblocks.arch import OpType
from coreblocks.params.configurations import test_core_config
from coreblocks.scheduler.scheduler import RSSelection
from transactron.lib import FIFO, Adapter, AdapterTrans
from transactron.testing import TestCaseWithSimulator, TestbenchIO, TestbenchContext
from transactron.testing.functions import data_const_to_dict
from transactron.testing.method_mock import MethodMock, def_method_mock

_rs1_optypes = {OpType.ARITHMETIC, OpType.COMPARE}
_rs2_optypes = {OpType.LOGIC, OpType.COMPARE}


class RSSelector(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params

    def elaborate(self, platform):
        m = Module()

        rs_layouts = self.gen_params.get(RSLayouts, rs_entries=self.gen_params.max_rs_entries)
        rf_layouts = self.gen_params.get(RFLayouts)
        scheduler_layouts = self.gen_params.get(SchedulerLayouts)

        # data structures
        m.submodules.instr_fifo = instr_fifo = FIFO(scheduler_layouts.rs_select_in, 2)
        m.submodules.out_fifo = out_fifo = FIFO(scheduler_layouts.rs_select_out, 2)

        # mocked input and output
        m.submodules.instr_in = self.instr_in = TestbenchIO(AdapterTrans(instr_fifo.write))
        m.submodules.instr_out = self.instr_out = TestbenchIO(AdapterTrans(out_fifo.read))
        m.submodules.rs1_alloc = self.rs1_alloc = TestbenchIO(Adapter.create(o=rs_layouts.rs.select_out))
        m.submodules.rs2_alloc = self.rs2_alloc = TestbenchIO(Adapter.create(o=rs_layouts.rs.select_out))
        m.submodules.rf_read_req1 = self.rf_read_req1 = TestbenchIO(Adapter.create(i=rf_layouts.rf_read_in))
        m.submodules.rf_read_req2 = self.rf_read_req2 = TestbenchIO(Adapter.create(i=rf_layouts.rf_read_in))

        # rs selector
        m.submodules.selector = self.selector = RSSelection(
            gen_params=self.gen_params,
            get_instr=instr_fifo.read,
            rs_select=[(self.rs1_alloc.adapter.iface, _rs1_optypes), (self.rs2_alloc.adapter.iface, _rs2_optypes)],
            push_instr=out_fifo.write,
            rf_read_req1=self.rf_read_req1.adapter.iface,
            rf_read_req2=self.rf_read_req2.adapter.iface,
        )

        return m


class TestRSSelect(TestCaseWithSimulator):
    def setup_method(self):
        self.gen_params = GenParams(test_core_config)
        self.m = RSSelector(self.gen_params)
        self.expected_out: deque[dict] = deque()
        self.instr_in: deque[dict] = deque()
        random.seed(1789)

    def create_instr_input_process(self, instr_count: int, optypes: set[OpType], random_wait: int = 0):
        async def process(sim: TestbenchContext):
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
                }

                self.instr_in.append(instr)
                await self.m.instr_in.call(sim, instr)
                await self.random_wait(sim, random_wait)

        return process

    def create_rs_alloc_process(self, io: TestbenchIO, rs_id: int, rs_optypes: set[OpType], enable_prob: float = 1):
        @def_method_mock(lambda: io, enable=lambda: random.random() <= enable_prob)
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

    @def_method_mock(lambda self: self.m.rf_read_req1)
    def rf_read_req1_mock(self, reg_id):
        pass

    @def_method_mock(lambda self: self.m.rf_read_req2)
    def rf_read_req2_mock(self, reg_id):
        pass

    def create_output_process(self, instr_count: int, random_wait: int = 0):
        async def process(sim: TestbenchContext):
            for _ in range(instr_count):
                result = await self.m.instr_out.call(sim)
                outputs = self.expected_out.popleft()

                await self.random_wait(sim, random_wait)
                assert data_const_to_dict(result) == outputs

        return process

    def test_base_functionality(self):
        """
        Test checking basic functionality when both RS select methods are available.
        """

        with self.run_simulation(self.m, max_cycles=1500) as sim:
            sim.add_testbench(self.create_instr_input_process(100, _rs1_optypes.union(_rs2_optypes)))
            self.add_mock(sim, self.create_rs_alloc_process(self.m.rs1_alloc, rs_id=0, rs_optypes=_rs1_optypes))
            self.add_mock(sim, self.create_rs_alloc_process(self.m.rs2_alloc, rs_id=1, rs_optypes=_rs2_optypes))
            sim.add_testbench(self.create_output_process(100))

    def test_only_rs1(self):
        """
        Test checking if instruction will get allocated if first the RS is full and
        the RS select method is not available.
        """

        with self.run_simulation(self.m, max_cycles=1500) as sim:
            sim.add_testbench(self.create_instr_input_process(100, _rs1_optypes.intersection(_rs2_optypes)))
            self.add_mock(sim, self.create_rs_alloc_process(self.m.rs1_alloc, rs_id=0, rs_optypes=_rs1_optypes))
            sim.add_testbench(self.create_output_process(100))

    def test_only_rs2(self):
        """
        Test checking if an instruction will get allocated if the second RS is full and
        the RS select method is not available.
        """

        with self.run_simulation(self.m, max_cycles=1500) as sim:
            sim.add_testbench(self.create_instr_input_process(100, _rs1_optypes.intersection(_rs2_optypes)))
            self.add_mock(sim, self.create_rs_alloc_process(self.m.rs2_alloc, rs_id=1, rs_optypes=_rs2_optypes))
            sim.add_testbench(self.create_output_process(100))

    def test_delays(self):
        """
        Test checking if instructions get allocated correctly if there are delays
        in methods availability.
        """

        with self.run_simulation(self.m, max_cycles=5000) as sim:
            sim.add_testbench(self.create_instr_input_process(300, _rs1_optypes.union(_rs2_optypes), random_wait=4))
            self.add_mock(
                sim, self.create_rs_alloc_process(self.m.rs1_alloc, rs_id=0, rs_optypes=_rs1_optypes, enable_prob=0.1)
            )
            self.add_mock(
                sim, self.create_rs_alloc_process(self.m.rs2_alloc, rs_id=1, rs_optypes=_rs2_optypes, enable_prob=0.1)
            )
            sim.add_testbench(self.create_output_process(300, random_wait=12))
