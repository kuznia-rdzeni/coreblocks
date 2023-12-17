from collections.abc import Callable
from typing import Any
from amaranth.sim import Passive
from contextlib import contextmanager
from .infrastructure import TestCaseWithSimulator
from coreblocks.params import GenParams
from coreblocks.utils.assertion import assert_bit, assert_bits
from transactron.utils import HasElaborate


__all__ = ["CoreblocksTestCaseWithSimulator", "make_assert_handler"]


def make_assert_handler(gen_params: GenParams, my_assert: Callable[[int, str], Any]):
    def assert_handler():
        yield Passive()
        while True:
            if not (yield assert_bit(gen_params)):
                for v, (n, i) in assert_bits(gen_params):
                    my_assert((yield v), f"Assertion at {n}:{i}")
            yield

    return assert_handler


class CoreblocksTestCaseWithSimulator(TestCaseWithSimulator):
    gen_params: GenParams

    @contextmanager
    def run_simulation(self, module: HasElaborate, max_cycles: float = 10e4, add_transaction_module=True):
        with super().run_simulation(module, max_cycles, add_transaction_module) as sim:
            assert_handler = make_assert_handler(self.gen_params, self.assertTrue)
            sim.add_sync_process(assert_handler)
            yield sim