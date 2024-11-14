import pytest
from transactron.lib import AdapterTrans, FIFO
from transactron.utils.amaranth_ext.elaboratables import ModuleConnector
from transactron.testing import TestCaseWithSimulator, TestbenchIO, SimpleTestCircuit, TestbenchContext

from coreblocks.frontend.decoder.decode_stage import DecodeStage
from coreblocks.params import GenParams
from coreblocks.arch import OpType, Funct3, Funct7
from coreblocks.interface.layouts import FetchLayouts, DecodeLayouts
from coreblocks.params.configurations import test_core_config


class TestDecode(TestCaseWithSimulator):
    @pytest.fixture(autouse=True)
    def setup(self, fixture_initialize_testing_env):
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

    async def decode_test_proc(self, sim: TestbenchContext):
        # testing an OP_IMM instruction (test copied from test_decoder.py)
        await self.fifo_in_write.call(sim, instr=0x02A28213)
        decoded = await self.fifo_out_read.call(sim)

        assert decoded["exec_fn"]["op_type"] == OpType.ARITHMETIC
        assert decoded["exec_fn"]["funct3"] == Funct3.ADD
        assert decoded["exec_fn"]["funct7"] == 0
        assert decoded["regs_l"]["rl_dst"] == 4
        assert decoded["regs_l"]["rl_s1"] == 5
        assert decoded["regs_l"]["rl_s2"] == 0
        assert decoded["imm"] == 42

        # testing an OP instruction (test copied from test_decoder.py)
        await self.fifo_in_write.call(sim, instr=0x003100B3)
        decoded = await self.fifo_out_read.call(sim)

        assert decoded["exec_fn"]["op_type"] == OpType.ARITHMETIC
        assert decoded["exec_fn"]["funct3"] == Funct3.ADD
        assert decoded["exec_fn"]["funct7"] == Funct7.ADD
        assert decoded["regs_l"]["rl_dst"] == 1
        assert decoded["regs_l"]["rl_s1"] == 2
        assert decoded["regs_l"]["rl_s2"] == 3

        # testing an illegal
        await self.fifo_in_write.call(sim, instr=0x0)
        decoded = await self.fifo_out_read.call(sim)

        assert decoded["exec_fn"]["op_type"] == OpType.EXCEPTION
        assert decoded["exec_fn"]["funct3"] == Funct3._EILLEGALINSTR
        assert decoded["exec_fn"]["funct7"] == 0
        assert decoded["regs_l"]["rl_dst"] == 0
        assert decoded["regs_l"]["rl_s1"] == 0
        assert decoded["regs_l"]["rl_s2"] == 0

        await self.fifo_in_write.call(sim, instr=0x0, access_fault=1)
        decoded = await self.fifo_out_read.call(sim)

        assert decoded["exec_fn"]["op_type"] == OpType.EXCEPTION
        assert decoded["exec_fn"]["funct3"] == Funct3._EINSTRACCESSFAULT
        assert decoded["exec_fn"]["funct7"] == 0
        assert decoded["regs_l"]["rl_dst"] == 0
        assert decoded["regs_l"]["rl_s1"] == 0
        assert decoded["regs_l"]["rl_s2"] == 0

    def test(self):
        with self.run_simulation(self.m) as sim:
            sim.add_testbench(self.decode_test_proc)
