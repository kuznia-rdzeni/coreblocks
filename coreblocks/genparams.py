from typing import TypeVar, Type

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
    log_regs_bits = 5

    def __init__(self, phys_regs_bits: int = 7, rob_entries_bits: int = 8):
        super().__init__()
        self.phys_regs_bits = phys_regs_bits
        self.rob_entries_bits = rob_entries_bits
