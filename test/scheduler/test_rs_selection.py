from collections import deque
import random

from amaranth import *
from amaranth.sim import Settle, Passive

from coreblocks.params import GenParams, RSLayouts, SchedulerLayouts, OpType, Opcode, Funct3, Funct7
from coreblocks.scheduler.scheduler import RSSelection
from coreblocks.transactions import TransactionModule
from coreblocks.transactions.lib import FIFO, Adapter, AdapterTrans
from coreblocks.utils import AutoDebugSignals
from test.common import TestCaseWithSimulator, TestbenchIO

_rs1_optypes = {OpType.ARITHMETIC, OpType.COMPARE}
_rs2_optypes = {OpType.LOGIC, OpType.COMPARE}


class RSSelector(Elaboratable, AutoDebugSignals):
    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params

    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        rs_layouts = self.gen_params.get(RSLayouts)
        scheduler_layouts = self.gen_params.get(SchedulerLayouts)

        with tm.transaction_context():
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

        return tm


class TestRSSelect(TestCaseWithSimulator):
    def setUp(self):
        self.gen_params = GenParams("rv32i", rs_number_bits=1)
        self.m = RSSelector(self.gen_params)
        self.expected_out = deque()
        self.instr_in = deque()
        random.seed(1789)

    def random_wait(self, n: int):
        for i in range(random.randint(0, n)):
            yield

    def create_instr_input_process(self, instr_count: int, optypes: set[OpType], random_wait: int = 0):
        def process():
            for i in range(instr_count):
                rp_dst = random.randint(0, self.gen_params.phys_regs_bits - 1)
                rp_s1 = random.randint(0, self.gen_params.phys_regs_bits - 1)
                rp_s2 = random.randint(0, self.gen_params.phys_regs_bits - 1)

                op_type = random.choice(list(optypes)).value
                funct3 = random.choice(list(Funct3)).value
                funct7 = random.choice(list(Funct7)).value

                opcode = random.choice(list(Opcode)).value
                immediate = random.randint(0, 2**32 - 1)

                rob_id = random.randint(0, self.gen_params.rob_entries_bits - 1)
                pc = random.randint(0, 2**32 - 1)

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
                    "pc": pc,
                }

                self.instr_in.append(instr)
                yield from self.m.instr_in.call(instr)
                yield from self.random_wait(random_wait)

        return process

    def create_rs_alloc_process(self, io: TestbenchIO, rs_id: int, random_wait: int = 0):
        def mock(_):
            random_entry = random.randint(0, self.gen_params.rs_entries - 1)
            expected = self.instr_in.popleft()
            expected["rs_entry_id"] = random_entry
            expected["rs_selected"] = rs_id
            self.expected_out.append(expected)

            return {"rs_entry_id": random_entry}

        def process():
            yield Passive()
            while True:
                yield from io.enable()
                yield from io.method_handle(mock, settle=1)
                yield from io.disable()
                yield from self.random_wait(random_wait)

        return process

    def create_output_process(self, instr_count: int, random_wait: int = 0):
        def check(got, expected):
            self.assertEqual(got, expected)

        def process():
            for _ in range(instr_count):
                result = yield from self.m.instr_out.call({})
                outputs = self.expected_out.popleft()

                yield from self.random_wait(random_wait)
                yield Settle()
                check(result, outputs)

        return process

    def test_base_functionality(self):
        with self.run_simulation(self.m, max_cycles=1500) as sim:
            sim.add_sync_process(self.create_instr_input_process(100, _rs1_optypes.union(_rs2_optypes)))
            sim.add_sync_process(self.create_rs_alloc_process(self.m.rs1_alloc, 0))
            sim.add_sync_process(self.create_rs_alloc_process(self.m.rs2_alloc, 1))
            sim.add_sync_process(self.create_output_process(100))

    def test_only_rs1(self):
        with self.run_simulation(self.m, max_cycles=1500) as sim:
            sim.add_sync_process(self.create_instr_input_process(100, _rs1_optypes.intersection(_rs2_optypes)))
            sim.add_sync_process(self.create_rs_alloc_process(self.m.rs1_alloc, 0))
            sim.add_sync_process(self.create_output_process(100))

    def test_only_rs2(self):
        with self.run_simulation(self.m, max_cycles=1500) as sim:
            sim.add_sync_process(self.create_instr_input_process(100, _rs1_optypes.intersection(_rs2_optypes)))
            sim.add_sync_process(self.create_rs_alloc_process(self.m.rs2_alloc, 1))
            sim.add_sync_process(self.create_output_process(100))

    def test_delays(self):
        with self.run_simulation(self.m, max_cycles=5000) as sim:
            sim.add_sync_process(self.create_instr_input_process(300, _rs1_optypes.union(_rs2_optypes), random_wait=4))
            sim.add_sync_process(self.create_rs_alloc_process(self.m.rs1_alloc, 0, random_wait=12))
            sim.add_sync_process(self.create_rs_alloc_process(self.m.rs2_alloc, 1, random_wait=12))
            sim.add_sync_process(self.create_output_process(300, random_wait=12))
