from typing import TypeVar, Type

from coreblocks.isa import ISA

__all__ = ["GenParams"]

T = TypeVar("T")


class DependentCache:
    def __init__(self):
        self._depcache = {}

    def get(self, cls: Type[T]) -> T:
        v = self._depcache.get(cls, None)
        if v is None:
            v = self._depcache[cls] = cls(self)
        return v


class GenParams(DependentCache):
    def __init__(self, isa_str: str):
        super().__init__()

        self.isa = ISA(isa_str)
