from transactron.lib import AdapterTrans, FIFO

from ..common import TestCaseWithSimulator, TestbenchIO, SimpleTestCircuit, ModuleConnector

from coreblocks.frontend.decode_stage import DecodeStage
from coreblocks.params import GenParams, FetchLayouts, DecodeLayouts, OpType, Funct3, Funct7
from coreblocks.params.configurations import test_core_config


class TestDecode(TestCaseWithSimulator):
    def setUp(self) -> None:
        self.gen_params = GenParams(test_core_config.replace(start_pc=24))

        fifo_in = FIFO(self.gen_params.get(FetchLayouts).raw_instr, depth=2)
        fifo_out = FIFO(self.gen_params.get(DecodeLayouts).decoded_instr, depth=2)

        self.fifo_in_write = TestbenchIO(AdapterTrans(fifo_in.write))
        self.fifo_out_read = TestbenchIO(AdapterTrans(fifo_out.read))

        self.decode = DecodeStage(self.gen_params, fifo_in.read, fifo_out.write)
        self.m = SimpleTestCircuit(
            ModuleConnector(
                decode=self.decode,
                fifo_in=fifo_in,
                fifo_out=fifo_out,
                fifo_in_write=self.fifo_in_write,
                fifo_out_read=self.fifo_out_read,
            )
        )

    def decode_test_proc(self):
        # testing an OP_IMM instruction (test copied from test_decoder.py)
        yield from self.fifo_in_write.call(instr=0x02A28213)
        decoded = yield from self.fifo_out_read.call()

        self.assertEqual(decoded["exec_fn"]["op_type"], OpType.ARITHMETIC)
        self.assertEqual(decoded["exec_fn"]["funct3"], Funct3.ADD)
        self.assertEqual(decoded["exec_fn"]["funct7"], 0)
        self.assertEqual(decoded["regs_l"]["rl_dst"], 4)
        self.assertEqual(decoded["regs_l"]["rl_s1"], 5)
        self.assertEqual(decoded["regs_l"]["rl_s2"], 0)
        self.assertEqual(decoded["imm"], 42)

        # testing an OP instruction (test copied from test_decoder.py)
        yield from self.fifo_in_write.call(instr=0x003100B3)
        decoded = yield from self.fifo_out_read.call()

        self.assertEqual(decoded["exec_fn"]["op_type"], OpType.ARITHMETIC)
        self.assertEqual(decoded["exec_fn"]["funct3"], Funct3.ADD)
        self.assertEqual(decoded["exec_fn"]["funct7"], Funct7.ADD)
        self.assertEqual(decoded["regs_l"]["rl_dst"], 1)
        self.assertEqual(decoded["regs_l"]["rl_s1"], 2)
        self.assertEqual(decoded["regs_l"]["rl_s2"], 3)

        # testing an illegal
        yield from self.fifo_in_write.call(instr=0x0)
        decoded = yield from self.fifo_out_read.call()

        self.assertEqual(decoded["exec_fn"]["op_type"], OpType.EXCEPTION)
        self.assertEqual(decoded["exec_fn"]["funct3"], Funct3._EILLEGALINSTR)
        self.assertEqual(decoded["exec_fn"]["funct7"], 0)
        self.assertEqual(decoded["regs_l"]["rl_dst"], 0)
        self.assertEqual(decoded["regs_l"]["rl_s1"], 0)
        self.assertEqual(decoded["regs_l"]["rl_s2"], 0)

        yield from self.fifo_in_write.call(instr=0x0, access_fault=1)
        decoded = yield from self.fifo_out_read.call()

        self.assertEqual(decoded["exec_fn"]["op_type"], OpType.EXCEPTION)
        self.assertEqual(decoded["exec_fn"]["funct3"], Funct3._EINSTRACCESSFAULT)
        self.assertEqual(decoded["exec_fn"]["funct7"], 0)
        self.assertEqual(decoded["regs_l"]["rl_dst"], 0)
        self.assertEqual(decoded["regs_l"]["rl_s1"], 0)
        self.assertEqual(decoded["regs_l"]["rl_s2"], 0)

    def test(self):
        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.decode_test_proc)
