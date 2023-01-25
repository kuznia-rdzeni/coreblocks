from __future__ import annotations

from coreblocks.peripherals.wishbone import WishboneMaster
import coreblocks.params.genparams as gp
from coreblocks.utils.protocols import FuncBlock, FuncUnit

__all__ = [
    "FuncUnitExtrasInputs",
    "FuncBlockExtrasInputs",
    "FuncBlockParams",
    "FuncUnitParams",
]


# extra constructor parameters of FuncUnit
class FuncUnitExtrasInputs:
    pass


# extra constructor parameters of FuncBlock
class FuncBlockExtrasInputs(FuncUnitExtrasInputs):
    def __init__(self, *, wishbone_bus: WishboneMaster):
        self.wishbone_bus = wishbone_bus


class FuncBlockParams:
    def get_module(self, gen_params: gp.GenParams, inputs: FuncBlockExtrasInputs) -> FuncBlock:
        ...


class FuncUnitParams:
    def get_module(self, gen_params: gp.GenParams, inputs: FuncUnitExtrasInputs) -> FuncUnit:
        ...
