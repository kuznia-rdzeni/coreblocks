from __future__ import annotations

from abc import abstractmethod, ABC
from dataclasses import dataclass, field
from typing import Iterable, Generic, TypeVar

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


class DependencyKey(Generic[T]):
    # TODO Make unifier optional
    unifier: type[Unifier]

    def get_unified(self, connections: "ComponentConnections"):
        unifiers = {}
        if len(connections.registered_methods[self]) == 1:
            method = connections.registered_methods[self][0]
        else:
            unifier_inst = self.unifier(connections.registered_methods[self])
            unifiers[self.__class__.__name__ + "_unifier"] = unifier_inst
            method = unifier_inst.method
        return method, unifiers


@dataclass(frozen=True)
class WishboneDataKey(DependencyKey[WishboneMaster]):
    pass


@dataclass(frozen=True)
class InstructionCommitKey(DependencyKey[Method]):
    unifier: type[Unifier] = field(default=MethodProduct, init=False)


@dataclass(frozen=True)
class BranchResolvedKey(DependencyKey[Method]):
    unifier: type[Unifier] = field(default=Collector, init=False)


# extra constructor parameters of FuncBlock
class ComponentConnections:
    def __init__(self):
        self.dependencies = {}
        self.registered_methods = {}

    def set_dependency(self, key: DependencyKey[T], dependency: T) -> ComponentConnections:
        self.dependencies[key] = dependency
        return self

    def register_method(self, key: DependencyKey[Method], method: Method) -> ComponentConnections:
        if key in self.registered_methods:
            self.registered_methods[key].append(method)
        else:
            self.registered_methods[key] = [method]
        return self

    def get_dependency(self, key: DependencyKey[T]) -> T:
        if key not in self.dependencies:
            raise Exception(f"Dependency {key} not provided")
        return self.dependencies[key]


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
