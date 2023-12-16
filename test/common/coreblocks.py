from amaranth.sim import Passive
from contextlib import contextmanager
from .infrastructure import TestCaseWithSimulator
from coreblocks.params import GenParams
from coreblocks.utils.assertion import assert_bit, assert_bits
from transactron.utils import HasElaborate


class CoreblocksTestCaseWithSimulator(TestCaseWithSimulator):
    gen_params: GenParams

    @contextmanager
    def run_simulation(self, module: HasElaborate, max_cycles: float = 10e4, add_transaction_module=True):
        def assert_handler():
            yield Passive()
            while True:
                if (yield assert_bit(self.gen_params)):
                    for v, (n, i) in assert_bits(self.gen_params):
                        self.assertTrue((yield v), f"Assertion at {n}:{i}")
                yield

        with super().run_simulation(module, max_cycles, add_transaction_module) as sim:
            sim.add_sync_process(assert_handler)
            yield sim
