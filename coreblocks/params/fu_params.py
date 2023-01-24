from __future__ import annotations
from typing import Iterable

from coreblocks.peripherals.wishbone import WishboneMaster
from coreblocks.transactions import Method
import coreblocks.params.genparams as gp
from coreblocks.utils.protocols import FuncBlock, FuncUnit

__all__ = [
    "FuncUnitExtrasOutputs",
    "FuncUnitExtrasInputs",
    "FuncBlockExtrasOutputs",
    "FuncBlockExtrasInputs",
    "FuncBlockParams",
    "FuncUnitParams",
]


# extra methods of FuncUnit
class FuncUnitExtrasOutputs:
    def __init__(self, *, branch_result: Method | None = None):
        self.branch_result = branch_result


# extra constructor parameters of FuncUnit
class FuncUnitExtrasInputs:
    pass


# extra methods of FuncBlock
class FuncBlockExtrasOutputs:
    def __init__(self, *, branch_result: Iterable[Method] | None = None, lsu_commit: Method | None = None):
        self.branch_result = branch_result
        self.lsu_commit = lsu_commit

    @staticmethod
    def from_func_units(fu_outputs: Iterable[FuncUnitExtrasOutputs]) -> "FuncBlockExtrasOutputs":
        branch_result = list(filter(lambda x: x is not None, map(lambda out: out.branch_result, fu_outputs)))
        return FuncBlockExtrasOutputs(branch_result=branch_result)


# extra constructor parameters of FuncBlock
class FuncBlockExtrasInputs(FuncUnitExtrasInputs):
    def __init__(self, *, wishbone_bus: WishboneMaster):
        self.wishbone_bus = wishbone_bus


class FuncBlockParams:
    def get_module(
        self, gen_params: gp.GenParams, inputs: FuncBlockExtrasInputs
    ) -> tuple[FuncBlock, FuncBlockExtrasOutputs]:
        ...


class FuncUnitParams:
    def get_module(
        self, gen_params: gp.GenParams, inputs: FuncUnitExtrasInputs
    ) -> tuple[FuncUnit, FuncUnitExtrasOutputs]:
        ...
