from __future__ import annotations

from inspect import signature
from typing import TypeVar, Type, Protocol, runtime_checkable
from amaranth.utils import log2_int

from .isa import ISA
from .fu_params import BlockComponentParams
from .icache_params import ICacheParameters
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
        icache_ways=2,
        icache_sets=128,
        icache_block_bytes=32,
    ):
        super().__init__()

        self.isa = ISA(isa_str)
        self.func_units_config = func_units_config

        bytes_in_word = self.isa.xlen // 8
        self.wb_params = WishboneParameters(
            data_width=self.isa.xlen, addr_width=self.isa.xlen - log2_int(bytes_in_word)
        )

        self.icache_params = ICacheParameters(
            addr_width=self.isa.xlen,
            word_width=self.isa.xlen,
            num_of_ways=icache_ways,
            num_of_sets=icache_sets,
            block_size_bytes=icache_block_bytes,
        )

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
