"""
This type stub file was generated by pyright.
"""

import functools
import inspect
from collections.abc import Iterable
from ...hdl.cd import ClockDomain
from ...hdl.ir import Fragment
from ...sim import *

__all__ = ["run_simulation", "passive"]

def run_simulation(fragment_or_module, generators, clocks=..., vcd_name=..., special_overrides=...): ...
def passive(generator): ...
