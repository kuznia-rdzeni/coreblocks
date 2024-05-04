from collections import defaultdict

from abc import abstractmethod, ABC
from typing import Any, Generic, TypeVar


__all__ = ["DependencyManager", "DependencyKey", "DependencyContext", "SimpleKey", "ListKey"]

T = TypeVar("T")
U = TypeVar("U")


class DependencyKey(Generic[T, U], ABC):
    """Base class for dependency keys.

    Dependency keys are used to access dependencies in the `DependencyManager`.
    Concrete instances of dependency keys should be frozen data classes.

    Parameters
    ----------
    lock_on_get: bool, default: True
        Specifies if no new dependencies should be added to key if it was already read by `get_dependency`.
    cache: bool, default: True
        If true, result of the `combine` method is cached and subsequent calls to `get_dependency`
        will return the value in the cache. Adding a new dependency clears the cache.
    empty_valid: bool, default : False
        Specifies if getting key dependency without any added dependencies is valid. If set to `False`, that
        action would cause raising `KeyError`.
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

    lock_on_get: bool = True
    cache: bool = True
    empty_valid: bool = False


class SimpleKey(Generic[T], DependencyKey[T, T]):
    """Base class for simple dependency keys.

    Simple dependency keys are used when there is an one-to-one relation between
    keys and dependencies. If more than one dependency is added to a simple key,
    an error is raised.

    Parameters
    ----------
    default_value: T
        Specifies the default value returned when no dependencies are added. To
        enable it `empty_valid` must be True.
    """

    default_value: T

    def combine(self, data: list[T]) -> T:
        if len(data) == 0:
            return self.default_value
        if len(data) != 1:
            raise RuntimeError(f"Key {self} assigned {len(data)} values, expected 1")
        return data[0]


class ListKey(Generic[T], DependencyKey[T, list[T]]):
    """Base class for list key.

    List keys are used when there is an one-to-many relation between keys
    and dependecies. Provides list of dependencies.
    """

    empty_valid = True

    def combine(self, data: list[T]) -> list[T]:
        return data


class DependencyManager:
    """Dependency manager.

    Tracks dependencies across the core.
    """

    def __init__(self):
        self.dependencies: defaultdict[DependencyKey, list] = defaultdict(list)
        self.cache: dict[DependencyKey, Any] = {}
        self.locked_dependencies: set[DependencyKey] = set()

    def add_dependency(self, key: DependencyKey[T, Any], dependency: T) -> None:
        """Adds a new dependency to a key.

        Depending on the key type, a key can have a single dependency or
        multple dependencies added to it.
        """

        if key in self.locked_dependencies:
            raise KeyError(f"Trying to add dependency to {key} that was already read and is locked")

        self.dependencies[key].append(dependency)

        if key in self.cache:
            del self.cache[key]

    def get_dependency(self, key: DependencyKey[Any, U]) -> U:
        """Gets the dependency for a key.

        The way dependencies are interpreted is dependent on the key type.
        """
        if not key.empty_valid and key not in self.dependencies:
            raise KeyError(f"Dependency {key} not provided")

        if key in self.cache:
            return self.cache[key]

        if key.lock_on_get:
            self.locked_dependencies.add(key)

        val = key.combine(self.dependencies[key])

        if key.cache:
            self.cache[key] = val

        return val


class DependencyContext:
    stack: list[DependencyManager] = []

    def __init__(self, manager: DependencyManager):
        self.manager = manager

    def __enter__(self):
        self.stack.append(self.manager)
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        top = self.stack.pop()
        assert self.manager is top

    @classmethod
    def get(cls) -> DependencyManager:
        if not cls.stack:
            raise RuntimeError("DependencyContext stack is empty")
        return cls.stack[-1]
