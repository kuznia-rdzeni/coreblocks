from __future__ import annotations
from collections import defaultdict

from abc import abstractmethod, ABC
from dataclasses import dataclass, field
from typing import Any, Iterable, Generic, TypeVar

import coreblocks.params.genparams as gp
import coreblocks.params.optypes as optypes
from coreblocks.transactions import Method
from coreblocks.utils.protocols import FuncBlock, FuncUnit, Unifier
from coreblocks.transactions.lib import MethodProduct, Collector
from coreblocks.peripherals.wishbone import WishboneMaster


__all__ = [
    "ComponentConnections",
    "BlockComponentParams",
    "FunctionalComponentParams",
    "optypes_supported",
    "DependencyKey",
    "WishboneDataKey",
    "InstructionCommitKey",
    "BranchResolvedKey",
]

T = TypeVar("T")
U = TypeVar("U")


class DependencyKey(Generic[T, U], ABC):
    @abstractmethod
    def combine(self, data: list[T]) -> U:
        raise NotImplementedError()


class SimpleKey(Generic[T], DependencyKey[T, T]):
    def combine(self, data: list[T]) -> T:
        if len(data) != 1:
            raise RuntimeError(f"Key {self} assigned {len(data)} values, expected 1")
        return data[0]


class UnifierKey(DependencyKey[Method, tuple[Method, dict[str, Unifier]]]):
    unifier: type[Unifier]

    def combine(self, data: list[Method]) -> tuple[Method, dict[str, Unifier]]:
        if len(data) == 1:
            return data[0], {}
        else:
            unifiers: dict[str, Unifier] = {}
            unifier_inst = self.unifier(data)
            unifiers[self.__class__.__name__ + "_unifier"] = unifier_inst
            method = unifier_inst.method
        return method, unifiers


@dataclass(frozen=True)
class WishboneDataKey(SimpleKey[WishboneMaster]):
    pass


@dataclass(frozen=True)
class InstructionCommitKey(UnifierKey):
    unifier: type[Unifier] = field(default=MethodProduct, init=False)


@dataclass(frozen=True)
class BranchResolvedKey(UnifierKey):
    unifier: type[Unifier] = field(default=Collector, init=False)


# extra constructor parameters of FuncBlock
class ComponentConnections:
    def __init__(self):
        self.dependencies = defaultdict[DependencyKey, list](list)

    def with_dependency(self, key: DependencyKey[T, Any], dependency: T) -> ComponentConnections:
        self.dependencies[key].append(dependency)
        return self

    def get_dependency(self, key: DependencyKey[Any, U]) -> U:
        if key not in self.dependencies:
            raise KeyError(f"Dependency {key} not provided")
        return key.combine(self.dependencies[key])


class BlockComponentParams(ABC):
    @abstractmethod
    def get_module(self, gen_params: gp.GenParams, connections: ComponentConnections) -> FuncBlock:
        raise NotImplementedError()

    @abstractmethod
    def get_optypes(self) -> set[optypes.OpType]:
        raise NotImplementedError()


class FunctionalComponentParams(ABC):
    @abstractmethod
    def get_module(self, gen_params: gp.GenParams, connections: ComponentConnections) -> FuncUnit:
        raise NotImplementedError()

    @abstractmethod
    def get_optypes(self) -> set[optypes.OpType]:
        raise NotImplementedError()


def optypes_supported(block_components: Iterable[BlockComponentParams]) -> set[optypes.OpType]:
    return {optype for block in block_components for optype in block.get_optypes()}
