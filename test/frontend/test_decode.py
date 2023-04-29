from amaranth import Elaboratable, Module

from coreblocks.transactions import TransactionModule
from coreblocks.transactions.lib import AdapterTrans, FIFO

from ..common import TestCaseWithSimulator, TestbenchIO

from coreblocks.frontend.decode import Decode
from coreblocks.params import GenParams, FetchLayouts, DecodeLayouts, OpType, Opcode, Funct3, Funct7
from coreblocks.params.configurations import test_core_config


class TestElaboratable(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.gp = gen_params

    def elaborate(self, platform):
        m = Module()

        fifo_in = FIFO(self.gp.get(FetchLayouts).raw_instr, depth=2)
        fifo_out = FIFO(self.gp.get(DecodeLayouts).decoded_instr, depth=2)

        self.io_in = TestbenchIO(AdapterTrans(fifo_in.write))
        self.io_out = TestbenchIO(AdapterTrans(fifo_out.read))

        self.decode = Decode(self.gp, fifo_in.read, fifo_out.write)

        m.submodules.decode = self.decode
        m.submodules.io_in = self.io_in
        m.submodules.io_out = self.io_out
        m.submodules.fifo_in = fifo_in
        m.submodules.fifo_out = fifo_out

        return m


class TestFetch(TestCaseWithSimulator):
    def setUp(self) -> None:
        self.gp = GenParams(test_core_config.replace(start_pc=24))
        self.test_module = TestElaboratable(self.gp)

    def decode_test_proc(self):
        # testing an OP_IMM instruction (test copied from test_decoder.py)
        yield from self.test_module.io_in.call(data=0x02A28213)
        decoded = yield from self.test_module.io_out.call()

        self.assertEqual(decoded["opcode"], Opcode.OP_IMM)
        self.assertEqual(decoded["illegal"], 0)
        self.assertEqual(decoded["exec_fn"]["op_type"], OpType.ARITHMETIC)
        self.assertEqual(decoded["exec_fn"]["funct3"], Funct3.ADD)
        self.assertEqual(decoded["regs_l"]["rl_dst"], 4)
        self.assertEqual(decoded["regs_l"]["rl_s1"], 5)
        self.assertEqual(decoded["regs_l"]["rl_s2"], 0)
        self.assertEqual(decoded["imm"], 42)

        # testing an OP instruction (test copied from test_decoder.py)
        yield from self.test_module.io_in.call(data=0x003100B3)
        decoded = yield from self.test_module.io_out.call()

        self.assertEqual(decoded["opcode"], Opcode.OP)
        self.assertEqual(decoded["illegal"], 0)
        self.assertEqual(decoded["exec_fn"]["op_type"], OpType.ARITHMETIC)
        self.assertEqual(decoded["exec_fn"]["funct3"], Funct3.ADD)
        self.assertEqual(decoded["exec_fn"]["funct7"], Funct7.ADD)
        self.assertEqual(decoded["regs_l"]["rl_dst"], 1)
        self.assertEqual(decoded["regs_l"]["rl_s1"], 2)
        self.assertEqual(decoded["regs_l"]["rl_s2"], 3)

    def test(self):
        with self.run_simulation(self.test_module) as sim:
            sim.add_sync_process(self.decode_test_proc)
