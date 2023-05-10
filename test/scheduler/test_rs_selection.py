from collections import deque
import random

from amaranth import *
from amaranth.sim import Settle, Passive

from coreblocks.params import GenParams, RSLayouts, SchedulerLayouts, OpType, Opcode, Funct3, Funct7
from coreblocks.params.configurations import test_core_config
from coreblocks.scheduler.scheduler import RSSelection
from coreblocks.transactions.lib import FIFO, Adapter, AdapterTrans
from test.common import TestCaseWithSimulator, TestbenchIO

_rs1_optypes = {OpType.ARITHMETIC, OpType.COMPARE}
_rs2_optypes = {OpType.LOGIC, OpType.COMPARE}


class RSSelector(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params

    def elaborate(self, platform):
        m = Module()

        rs_layouts = self.gen_params.get(RSLayouts)
        scheduler_layouts = self.gen_params.get(SchedulerLayouts)

        # data structures
        m.submodules.instr_fifo = instr_fifo = FIFO(scheduler_layouts.rs_select_in, 2)
        m.submodules.out_fifo = out_fifo = FIFO(scheduler_layouts.rs_select_out, 2)

        # mocked input and output
        m.submodules.instr_in = self.instr_in = TestbenchIO(AdapterTrans(instr_fifo.write))
        m.submodules.instr_out = self.instr_out = TestbenchIO(AdapterTrans(out_fifo.read))
        m.submodules.rs1_alloc = self.rs1_alloc = TestbenchIO(Adapter(o=rs_layouts.select_out))
        m.submodules.rs2_alloc = self.rs2_alloc = TestbenchIO(Adapter(o=rs_layouts.select_out))

        # rs selector
        m.submodules.selector = self.selector = RSSelection(
            gen_params=self.gen_params,
            get_instr=instr_fifo.read,
            rs_select=[(self.rs1_alloc.adapter.iface, _rs1_optypes), (self.rs2_alloc.adapter.iface, _rs2_optypes)],
            push_instr=out_fifo.write,
        )

        return m


class TestRSSelect(TestCaseWithSimulator):
    def setUp(self):
        self.gen_params = GenParams(test_core_config)
        self.m = RSSelector(self.gen_params)
        self.expected_out = deque()
        self.instr_in = deque()
        random.seed(1789)

    def random_wait(self, n: int):
        for i in range(random.randrange(n + 1)):
            yield

    def create_instr_input_process(self, instr_count: int, optypes: set[OpType], random_wait: int = 0):
        def process():
            for i in range(instr_count):
                rp_dst = random.randrange(self.gen_params.phys_regs_bits)
                rp_s1 = random.randrange(self.gen_params.phys_regs_bits)
                rp_s2 = random.randrange(self.gen_params.phys_regs_bits)

                op_type = random.choice(list(optypes))
                funct3 = random.choice(list(Funct3))
                funct7 = random.choice(list(Funct7))

                opcode = random.choice(list(Opcode))
                immediate = random.randrange(2**32)

                rob_id = random.randrange(self.gen_params.rob_entries_bits)
                pc = random.randrange(2**32)
                csr = random.randrange(2**self.gen_params.isa.csr_alen)

                instr = {
                    "opcode": opcode,
                    "illegal": 0,
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
                yield from self.m.instr_in.call(instr)
                yield from self.random_wait(random_wait)

        return process

    def create_rs_alloc_process(self, io: TestbenchIO, rs_id: int, rs_optypes: set[OpType], random_wait: int = 0):
        def mock():
            random_entry = random.randrange(self.gen_params.rs_entries)
            expected = self.instr_in.popleft()
            self.assertIn(expected["exec_fn"]["op_type"], rs_optypes)
            expected["rs_entry_id"] = random_entry
            expected["rs_selected"] = rs_id
            self.expected_out.append(expected)

            return {"rs_entry_id": random_entry}

        def process():
            yield Passive()
            while True:
                yield from io.enable()
                yield from io.method_handle(mock)
                yield from io.disable()
                yield from self.random_wait(random_wait)

        return process

    def create_output_process(self, instr_count: int, random_wait: int = 0):
        def process():
            for _ in range(instr_count):
                result = yield from self.m.instr_out.call()
                outputs = self.expected_out.popleft()

                yield from self.random_wait(random_wait)
                yield Settle()
                self.assertEqual(result, outputs)

        return process

    def test_base_functionality(self):
        """
        Test checking basic functionality when both RS select methods are available.
        """

        with self.run_simulation(self.m, max_cycles=1500) as sim:
            sim.add_sync_process(self.create_instr_input_process(100, _rs1_optypes.union(_rs2_optypes)))
            sim.add_sync_process(self.create_rs_alloc_process(self.m.rs1_alloc, rs_id=0, rs_optypes=_rs1_optypes))
            sim.add_sync_process(self.create_rs_alloc_process(self.m.rs2_alloc, rs_id=1, rs_optypes=_rs2_optypes))
            sim.add_sync_process(self.create_output_process(100))

    def test_only_rs1(self):
        """
        Test checking if instruction will get allocated if first the RS is full and
        the RS select method is not available.
        """

        with self.run_simulation(self.m, max_cycles=1500) as sim:
            sim.add_sync_process(self.create_instr_input_process(100, _rs1_optypes.intersection(_rs2_optypes)))
            sim.add_sync_process(self.create_rs_alloc_process(self.m.rs1_alloc, rs_id=0, rs_optypes=_rs1_optypes))
            sim.add_sync_process(self.create_output_process(100))

    def test_only_rs2(self):
        """
        Test checking if an instruction will get allocated if the second RS is full and
        the RS select method is not available.
        """

        with self.run_simulation(self.m, max_cycles=1500) as sim:
            sim.add_sync_process(self.create_instr_input_process(100, _rs1_optypes.intersection(_rs2_optypes)))
            sim.add_sync_process(self.create_rs_alloc_process(self.m.rs2_alloc, rs_id=1, rs_optypes=_rs2_optypes))
            sim.add_sync_process(self.create_output_process(100))

    def test_delays(self):
        """
        Test checking if instructions get allocated correctly if there are delays
        in methods availability.
        """

        with self.run_simulation(self.m, max_cycles=5000) as sim:
            sim.add_sync_process(self.create_instr_input_process(300, _rs1_optypes.union(_rs2_optypes), random_wait=4))
            sim.add_sync_process(
                self.create_rs_alloc_process(self.m.rs1_alloc, rs_id=0, rs_optypes=_rs1_optypes, random_wait=12)
            )
            sim.add_sync_process(
                self.create_rs_alloc_process(self.m.rs2_alloc, rs_id=1, rs_optypes=_rs2_optypes, random_wait=12)
            )
            sim.add_sync_process(self.create_output_process(300, random_wait=12))
