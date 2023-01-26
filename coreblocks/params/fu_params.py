from __future__ import annotations

from typing import Iterable

import coreblocks.params.genparams as gp
import coreblocks.params.optypes as optypes
from coreblocks.peripherals.wishbone import WishboneMaster
from coreblocks.utils.protocols import FuncBlock, FuncUnit

__all__ = [
    "FunctionalComponentInputs",
    "BlockComponentInputs",
    "BlockComponentParams",
    "FunctionalComponentParams",
    "optypes_supported",
]


# extra constructor parameters of FuncUnit
class FunctionalComponentInputs:
    pass


# extra constructor parameters of FuncBlock
class BlockComponentInputs(FunctionalComponentInputs):
    def __init__(self, *, wishbone_bus: WishboneMaster):
        self.wishbone_bus = wishbone_bus


class BlockComponentParams:
    def get_module(self, gen_params: gp.GenParams, inputs: BlockComponentInputs) -> FuncBlock:
        ...

    def get_optypes(self) -> set[optypes.OpType]:
        ...


class FunctionalComponentParams:
    def get_module(self, gen_params: gp.GenParams, inputs: FunctionalComponentInputs) -> FuncUnit:
        ...

    def get_optypes(self) -> set[optypes.OpType]:
        ...


def optypes_supported(block_components: Iterable[BlockComponentParams]) -> set[optypes.OpType]:
    return {optype for block in block_components for optype in block.get_optypes()}
