from __future__ import annotations

from abc import abstractmethod
from typing import Iterable, Generic, TypeVar

import coreblocks.params.genparams as gp
import coreblocks.params.optypes as optypes
from coreblocks.utils.protocols import FuncBlock, FuncUnit

__all__ = [
    "ComponentDependencies",
    "BlockComponentParams",
    "FunctionalComponentParams",
    "optypes_supported",
]

T = TypeVar("T")


class Key(Generic[T]):
    def __init__(self, name: str):
        self.name = name


# extra constructor parameters of FuncBlock
class ComponentDependencies:
    def __init__(self, **dependencies):
        self.dependencies = dependencies

    def get(self, key: Key[T]) -> T:
        if key.name not in self.dependencies:
            raise Exception(f"Dependency {key.name} not provided")
        return self.dependencies[key.name]


class BlockComponentParams:
    @abstractmethod
    def get_module(self, gen_params: gp.GenParams, dependencies: ComponentDependencies) -> FuncBlock:
        ...

    @abstractmethod
    def get_optypes(self) -> set[optypes.OpType]:
        ...


class FunctionalComponentParams:
    @abstractmethod
    def get_module(self, gen_params: gp.GenParams, dependencies: ComponentDependencies) -> FuncUnit:
        ...

    @abstractmethod
    def get_optypes(self) -> set[optypes.OpType]:
        ...


def optypes_supported(block_components: Iterable[BlockComponentParams]) -> set[optypes.OpType]:
    return {optype for block in block_components for optype in block.get_optypes()}
