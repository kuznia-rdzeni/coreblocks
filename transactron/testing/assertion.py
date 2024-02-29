from collections.abc import Callable
from typing import Any
from amaranth.sim import Passive, Tick
from transactron.utils import assert_bit, assert_bits
from transactron.utils.dependencies import DependencyContext


__all__ = ["make_assert_handler"]


def make_assert_handler(my_assert: Callable[[int, str], Any]):
    dependency_manager = DependencyContext.get()

    def assert_handler():
        yield Passive()
        while True:
            yield Tick("sync_neg")
            if not (yield assert_bit(dependency_manager)):
                for v, (n, i) in assert_bits(dependency_manager):
                    my_assert((yield v), f"Assertion at {n}:{i}")
            yield

    return assert_handler
