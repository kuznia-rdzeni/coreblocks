from typing import TypeVar, Type
from .isa import ISA
from .mul_params import MulUnitParams

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
    def __init__(
        self,
        isa_str: str,
        *,
        phys_regs_bits: int = 7,
        rob_entries_bits: int = 8,
        rs_entries: int = 4,
        start_pc: int = 0,
        mul_unit_params: MulUnitParams = MulUnitParams.ShiftMultiplier()
    ):
        super().__init__()
        self.isa = ISA(isa_str)

        self.phys_regs_bits = phys_regs_bits
        self.rob_entries_bits = rob_entries_bits
        self.rs_entries = rs_entries
        self.rs_entries_bits = (rs_entries - 1).bit_length()
        self.start_pc = start_pc
        self.mul_unit_params = mul_unit_params
        self.func_units = 1
