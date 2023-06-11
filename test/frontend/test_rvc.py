from amaranth.sim import Settle

from coreblocks.frontend.rvc import InstrDecompress

from coreblocks.params import *
from coreblocks.params.configurations import test_core_config
from coreblocks.utils import ModuleConnector
from ..common import TestCaseWithSimulator, def_method_mock


class TestInstrDecompress(TestCaseWithSimulator):
    TEST_CASES = [
        (0x0000, IllegalInstr()), # Illegal instruction
    ]

    def setUp(self) -> None:
        self.gp = GenParams(test_core_config.replace(compressed=True))

        self.m = InstrDecompress(self.gp)

    def test(self):
        def process():
            for instr_in, instr_out in TestInstrDecompress.TEST_CASES:
                yield self.rvc.instr_in.eq(instr_in)
                yield Settle()
                self.assertEqual((yield self.m.instr_out), (yield instr_out))
                yield

        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(process)
