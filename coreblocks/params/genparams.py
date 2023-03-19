from __future__ import annotations

from inspect import signature
from typing import TypeVar, Type, Protocol, runtime_checkable

from .isa import ISA
from .fu_params import BlockComponentParams
from ..peripherals.wishbone import WishboneParameters

__all__ = ["GenParams"]

T = TypeVar("T")


class DependentCache:
    def __init__(self):
        self._depcache = {}

    def get(self, cls: Type[T]) -> T:
        v = self._depcache.get(cls, None)
        if v is None:
            sig = signature(cls)
            if sig.parameters:
                v = cls(self)
            else:
                v = cls()
            self._depcache[cls] = v
        return v


class GenParams(DependentCache):
    def __init__(
        self,
        isa_str: str,
        func_units_config: list[BlockComponentParams],
        *,
        phys_regs_bits: int = 6,
        rob_entries_bits: int = 7,
        start_pc: int = 0,
    ):
        super().__init__()

        self.isa = ISA(isa_str)
        self.func_units_config = func_units_config
        self.bus_params = WishboneParameters(self.isa.xlen, self.isa.xlen)

        # Verification temporally disabled
        # if not optypes_required_by_extensions(self.isa.extensions) <= optypes_supported(func_units_config):
        #     raise Exception(f"Functional unit configuration fo not support all extension required by{isa_str}")

        self.rs_entries = 1

        @runtime_checkable
        class HasRSEntries(Protocol):
            rs_entries: int

        for block in self.func_units_config:
            if isinstance(block, HasRSEntries):
                self.rs_entries = max(self.rs_entries, block.rs_entries)

        self.rs_number_bits = (len(self.func_units_config) - 1).bit_length()

        self.phys_regs_bits = phys_regs_bits
        self.rob_entries_bits = rob_entries_bits
        self.rs_entries_bits = (self.rs_entries - 1).bit_length()
        self.start_pc = start_pc
