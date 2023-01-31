from __future__ import annotations

from typing import Iterable

import coreblocks.params.genparams as gp
import coreblocks.params.optypes as optypes
from coreblocks.utils.protocols import FuncBlock, FuncUnit

__all__ = [
    "ComponentDependencies",
    "BlockComponentParams",
    "FunctionalComponentParams",
    "optypes_supported",
]


# extra constructor parameters of FuncBlock
class ComponentDependencies:
    def __init__(self, **dependencies):
        self.dependencies = dependencies

    def __getattr__(self, item):
        if item in self.dependencies:
            return self.dependencies[item]
        else:
            return None


class BlockComponentParams:
    def get_module(self, gen_params: gp.GenParams, dependencies: ComponentDependencies) -> FuncBlock:
        ...

    def get_optypes(self) -> set[optypes.OpType]:
        ...


class FunctionalComponentParams:
    def get_module(self, gen_params: gp.GenParams, dependencies: ComponentDependencies) -> FuncUnit:
        ...

    def get_optypes(self) -> set[optypes.OpType]:
        ...


def optypes_supported(block_components: Iterable[BlockComponentParams]) -> set[optypes.OpType]:
    return {optype for block in block_components for optype in block.get_optypes()}
