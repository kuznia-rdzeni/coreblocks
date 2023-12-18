from amaranth import *

from coreblocks.params.genparams import GenParams
from coreblocks.params.configurations import basic_core_config
from transactron.utils import assertion
from ..common import CoreblocksTestCaseWithSimulator


class AssertionTest(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params
        self.input = Signal()
        self.output = Signal()

    def elaborate(self, platform):
        m = Module()

        m.d.comb += self.output.eq(self.input & ~self.input)

        assertion(self.gen_params, self.input == self.output)

        return m


class TestAssertion(CoreblocksTestCaseWithSimulator):
    def setUp(self):
        self.gen_params = GenParams(basic_core_config)

    def test_assertion(self):
        m = AssertionTest(self.gen_params)

        def proc():
            yield
            yield m.input.eq(1)

        with self.assertRaises(AssertionError):
            with self.run_simulation(m) as sim:
                sim.add_sync_process(proc)
