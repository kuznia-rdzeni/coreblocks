from __future__ import annotations

from abc import abstractmethod, ABC
from dataclasses import dataclass, field
from typing import Iterable, Generic, TypeVar

import coreblocks.params.genparams as gp
import coreblocks.params.optypes as optypes
from coreblocks.params import blocks_method_unifiers
from coreblocks.transactions import Method
from coreblocks.utils.protocols import FuncBlock, FuncUnit

__all__ = [
    "ComponentConnections",
    "BlockComponentParams",
    "FunctionalComponentParams",
    "optypes_supported",
    "DependencyKey",
    "InstructionCommitKey",
    "BranchResolvedKey"
]

T = TypeVar("T")


@dataclass
class DependencyKey(Generic[T]):
    name: str
    dep_type: type[T]

    def __hash__(self):
        return hash(self.name) ^ (hash(self.dep_type)*2)

    #TODO Add test for RO
    def __setattr__(self, n, v):
        if hasattr(self, n) and (n == "name" or n == "dep_type"):
            raise RuntimeError("Modifing ro field")
        super().__setattr__(n, v)

@dataclass
class InstructionCommitKey(DependencyKey[Method]):
    name : str = field(default="commit", init=False)
    dep_type : type[Method] = field(default=Method, init=False)

    def __hash__(self):
        return super().__hash__()

@dataclass
class BranchResolvedKey(DependencyKey[Method]):
    name : str = field(default="branch_result", init=False)
    dep_type : type[Method] = field(default=Method, init=False)

    def __hash__(self):
        return super().__hash__()

# extra constructor parameters of FuncBlock
class ComponentConnections:
    def __init__(self):
        self.dependencies = {}
        self.registered_methods = {}

    def set_dependency(self, key: DependencyKey[T], dependency: T) -> ComponentConnections:
        self.dependencies[key] = dependency
        return self

    def register_method(self, key: DependencyKey[T], method: Method) -> ComponentConnections:
        if method.name in self.registered_methods:
            if method.name in blocks_method_unifiers:
                self.registered_methods[method.name].append(method)
            else:
                raise Exception(f"Cannot handle multiple {method.name} methods without unifier")
        else:
            self.registered_methods[method.name] = [method]
        return self

    def register_dependency(self, key: DependencyKey[T]) -> T:
        if key not in self.dependencies:
            raise Exception(f"Dependency {key.name} not provided")
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
