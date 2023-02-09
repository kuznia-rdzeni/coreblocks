from __future__ import annotations

from abc import abstractmethod, ABC
from typing import Iterable, Generic, TypeVar, Protocol

import coreblocks.params.genparams as gp
import coreblocks.params.optypes as optypes
from coreblocks.transactions import Method
from coreblocks.utils.protocols import FuncBlock, FuncUnit

__all__ = [
    "ComponentConnections",
    "BlockComponentParams",
    "FunctionalComponentParams",
    "optypes_supported",
    "Unifier",
    "DependencyKey",
    "OutputKey",
]

T = TypeVar("T")


class Unifier(Protocol):
    method: Method

    @abstractmethod
    def __init__(self, targets: list[Method]):
        ...


class DependencyKey(Generic[T], ABC):
    pass


class OutputKey(ABC):
    @classmethod
    @abstractmethod
    def unifier(cls) -> type[Unifier] | None:
        return None

    @classmethod
    @abstractmethod
    def method_name(cls) -> str:
        ...


# extra constructor parameters of FuncBlock
class ComponentConnections:
    def __init__(self):
        self.dependencies = {}
        self.outputs = {}

    def set_dependency(self, key: type[DependencyKey[T]], dependency: T) -> ComponentConnections:
        self.dependencies[key] = dependency
        return self

    def set_output(self, key: type[OutputKey], output: Method) -> ComponentConnections:
        if key in self.outputs:
            if key.unifier() is not None:
                self.outputs[key].append(output)
            else:
                raise Exception(f"Cannot handle multiple {key} without unifier")
        else:
            self.outputs[key] = [output]
        return self

    def get_dependency(self, key: type[DependencyKey[T]]) -> T:
        if key not in self.dependencies:
            raise Exception(f"Dependency {key} not provided")
        return self.dependencies[key]

    def get_outputs(self) -> dict[type[OutputKey], list[Method]]:
        return self.outputs


class BlockComponentParams(ABC):
    @abstractmethod
    def get_module(self, gen_params: gp.GenParams, connections: ComponentConnections) -> FuncBlock:
        ...

    @abstractmethod
    def get_optypes(self) -> set[optypes.OpType]:
        ...


class FunctionalComponentParams(ABC):
    @abstractmethod
    def get_module(self, gen_params: gp.GenParams, connections: ComponentConnections) -> FuncUnit:
        ...

    @abstractmethod
    def get_optypes(self) -> set[optypes.OpType]:
        ...


def optypes_supported(block_components: Iterable[BlockComponentParams]) -> set[optypes.OpType]:
    return {optype for block in block_components for optype in block.get_optypes()}
