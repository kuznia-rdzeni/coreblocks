from __future__ import annotations
from collections import defaultdict

from abc import abstractmethod, ABC
from typing import Any, Iterable, Generic, TypeVar

import coreblocks.params.genparams as gp
import coreblocks.params.optypes as optypes
from coreblocks.transactions import Method
from coreblocks.utils.protocols import FuncBlock, FuncUnit, Unifier


__all__ = [
    "DependencyManager",
    "BlockComponentParams",
    "FunctionalComponentParams",
    "optypes_supported",
    "DependencyKey",
]

T = TypeVar("T")
U = TypeVar("U")


class DependencyKey(Generic[T, U], ABC):
    """Base class for dependency keys.

    Dependency keys are used to access dependencies in the `DependencyManager`.
    Concrete instances of dependency keys should be frozen data classes.
    """

    @abstractmethod
    def combine(self, data: list[T]) -> U:
        """Combine multiple dependencies with the same key.

        This method is used to generate the value returned from `get_dependency`
        in the `DependencyManager`. It takes dependencies added to the key
        using `add_dependency` and combines them to a single result.

        Different implementations of `combine` give different combining behavior
        for different kinds of keys.
        """
        raise NotImplementedError()

    @abstractmethod
    def __hash__(self) -> int:
        """The `__hash__` method is made abstract so that only concrete keys
        can be instanced. It is automatically overridden in frozen data
        classes.
        """
        raise NotImplementedError()


class SimpleKey(Generic[T], DependencyKey[T, T]):
    """Base class for simple dependency keys.

    Simple dependency keys are used when there is an one-to-one relation between
    keys and dependencies. If more than one dependency is added to a simple key,
    an error is raised.
    """

    def combine(self, data: list[T]) -> T:
        if len(data) != 1:
            raise RuntimeError(f"Key {self} assigned {len(data)} values, expected 1")
        return data[0]


class ListKey(Generic[T], DependencyKey[T, list[T]]):
    """Base class for list key.

    List keys are useed when there is an one-to-many relation between keys
    and dependecies. Provides list of dependencies.
    """

    def combine(self, data: list[T]) -> list[T]:
        return data


class UnifierKey(DependencyKey[Method, tuple[Method, dict[str, Unifier]]]):
    """Base class for method unifier dependency keys.

    Method unifier dependency keys are used to collect methods to be called by
    some part of the core. As multiple modules may wish to be called, a method
    unifier is used to present a single method interface to the caller, which
    allows to customize the calling behavior.
    """

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


class DependencyManager:
    """Dependency manager.

    Tracks dependencies across the core.
    """

    def __init__(self):
        self.dependencies = defaultdict[DependencyKey, list](list)

    def add_dependency(self, key: DependencyKey[T, Any], dependency: T) -> None:
        """Adds a new dependency to a key.

        Depending on the key type, a key can have a single dependency or
        multple dependencies added to it.
        """
        self.dependencies[key].append(dependency)

    def get_dependency(self, key: DependencyKey[Any, U]) -> U:
        """Gets the dependency for a key.

        The way dependencies are interpreted is dependent on the key type.
        """
        if key not in self.dependencies:
            raise KeyError(f"Dependency {key} not provided")
        return key.combine(self.dependencies[key])


class BlockComponentParams(ABC):
    @abstractmethod
    def get_module(self, gen_params: gp.GenParams) -> FuncBlock:
        raise NotImplementedError()

    @abstractmethod
    def get_optypes(self) -> set[optypes.OpType]:
        raise NotImplementedError()


class FunctionalComponentParams(ABC):
    @abstractmethod
    def get_module(self, gen_params: gp.GenParams) -> FuncUnit:
        raise NotImplementedError()

    @abstractmethod
    def get_optypes(self) -> set[optypes.OpType]:
        raise NotImplementedError()


def optypes_supported(block_components: Iterable[BlockComponentParams]) -> set[optypes.OpType]:
    return {optype for block in block_components for optype in block.get_optypes()}
