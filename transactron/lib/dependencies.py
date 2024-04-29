from collections.abc import Callable

from .. import Method
from .transformers import Unifier
from ..utils.dependencies import *


__all__ = ["DependencyManager", "DependencyKey", "SimpleKey", "ListKey", "UnifierKey"]


class UnifierKey(DependencyKey["Method", tuple["Method", dict[str, "Unifier"]]]):
    """Base class for method unifier dependency keys.

    Method unifier dependency keys are used to collect methods to be called by
    some part of the core. As multiple modules may wish to be called, a method
    unifier is used to present a single method interface to the caller, which
    allows to customize the calling behavior.
    """

    unifier: Callable[[list["Method"]], "Unifier"]

    def __init_subclass__(cls, unifier: Callable[[list["Method"]], "Unifier"], **kwargs) -> None:
        cls.unifier = unifier
        return super().__init_subclass__(**kwargs)

    def combine(self, data: list["Method"]) -> tuple["Method", dict[str, "Unifier"]]:
        if len(data) == 1:
            return data[0], {}
        else:
            unifiers: dict[str, Unifier] = {}
            unifier_inst = self.unifier(data)
            unifiers[self.__class__.__name__ + "_unifier"] = unifier_inst
            method = unifier_inst.method
        return method, unifiers
