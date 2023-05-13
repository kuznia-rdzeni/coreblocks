from __future__ import annotations

from inspect import signature
from typing import TypeVar, Type, Protocol, runtime_checkable
from amaranth.utils import log2_int

from .isa import ISA, gen_isa_string
from .icache_params import ICacheParameters
from .fu_params import extensions_supported
from ..peripherals.wishbone import WishboneParameters

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .configurations import CoreConfiguration

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
    def __init__(self, cfg: CoreConfiguration):
        super().__init__()

        self.func_units_config = cfg.func_units_config

        ext_parital, ext_full = extensions_supported(self.func_units_config)
        extensions = ext_parital
        extensions |= cfg._implied_extensions
        self.isa_str = gen_isa_string(extensions, cfg.xlen)

        self.isa = ISA(self.isa_str)

        bytes_in_word = self.isa.xlen // 8
        self.wb_params = WishboneParameters(
            data_width=self.isa.xlen, addr_width=self.isa.xlen - log2_int(bytes_in_word)
        )

        self.icache_params = ICacheParameters(
            addr_width=self.isa.xlen,
            word_width=self.isa.xlen,
            num_of_ways=cfg.icache_ways,
            num_of_sets_bits=cfg.icache_sets_bits,
            block_size_bits=cfg.icache_block_size_bits,
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

        self.phys_regs_bits = cfg.phys_regs_bits
        self.rob_entries_bits = cfg.rob_entries_bits
        self.rs_entries_bits = (self.rs_entries - 1).bit_length()
        self.start_pc = cfg.start_pc
