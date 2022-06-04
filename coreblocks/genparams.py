from typing import TypeVar, Type
from .isa import ISA

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
    def __init__(self, isa_str, *, phys_regs_bits=8, rob_entries_bits=7, rs_entries=4):
        super().__init__()
        self.isa = ISA(isa_str)

        self.phys_regs_bits = phys_regs_bits
        self.rob_entries_bits = rob_entries_bits
        self.rs_entries = rs_entries
        self.rs_entries_bits = rs_entries.bit_length() - 1
