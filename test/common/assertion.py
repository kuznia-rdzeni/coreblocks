from collections.abc import Callable
from typing import Any
from amaranth.sim import Passive, Delay
from transactron.utils import assert_bit, assert_bits
from transactron.utils.dependencies import DependencyManager


__all__ = ["make_assert_handler"]


def make_assert_handler(dependency_manager: DependencyManager, my_assert: Callable[[int, str], Any], clk_period: float):
    def assert_handler():
        yield Passive()
        while True:
            yield Delay((1 - 1e-4) * clk_period)  # Shorter than clock cycle
            if not (yield assert_bit(dependency_manager)):
                for v, (n, i) in assert_bits(dependency_manager):
                    my_assert((yield v), f"Assertion at {n}:{i}")
            yield

    return assert_handler
