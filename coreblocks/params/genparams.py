from __future__ import annotations

from typing import TypeVar, Type, Any
from amaranth.utils import log2_int

from .isa import ISA, gen_isa_string
from .icache_params import ICacheParameters
from .fu_params import extensions_supported
from ..peripherals.wishbone import WishboneParameters
from transactron.utils import make_hashable

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .configurations import CoreConfiguration

__all__ = ["GenParams"]

T = TypeVar("T")


class DependentCache:
    """
    Cache for classes, that depend on the `DependentCache` class itself.

    Cached classes may accept one positional argument in the constructor, where this `DependentCache` class will
    be passed. Classes may define any number keyword arguments in the constructor and separate cache entry will
    be created for each set of the arguments.

    Methods
    -------
    get: T, **kwargs -> T
        Gets class `cls` from cache. Caches `cls` reference if this is the first call for it.
        Optionally accepts `kwargs` for additional arguments in `cls` constructor.

    """

    def __init__(self):
        self._depcache: dict[tuple[Type, Any], Type] = {}

    def get(self, cls: Type[T], **kwargs) -> T:
        cache_key = make_hashable(kwargs)
        v = self._depcache.get((cls, cache_key), None)
        if v is None:
            positional_count = cls.__init__.__code__.co_argcount

            # first positional arg is `self` field, second may be `DependentCache`
            if positional_count > 2:
                raise KeyError(f"Too many positional arguments in {cls!r} constructor")

            if positional_count > 1:
                v = cls(self, **kwargs)
            else:
                v = cls(**kwargs)
            self._depcache[(cls, cache_key)] = v
        return v


class GenParams(DependentCache):
    def __init__(self, cfg: CoreConfiguration):
        super().__init__()

        self.func_units_config = cfg.func_units_config

        ext_partial, ext_full = extensions_supported(self.func_units_config, cfg.embedded, cfg.compressed)
        extensions = ext_partial if cfg.allow_partial_extensions else ext_full
        if not cfg.allow_partial_extensions and ext_partial != ext_full:
            raise RuntimeError(f"Extensions {ext_partial&~ext_full!r} are only partially supported")

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

        self.max_rs_entries = 1

        for block in self.func_units_config:
            self.max_rs_entries = max(self.max_rs_entries, block.get_rs_entry_count())

        self.rs_number_bits = (len(self.func_units_config) - 1).bit_length()

        self.phys_regs_bits = cfg.phys_regs_bits
        self.rob_entries_bits = cfg.rob_entries_bits
        self.max_rs_entries_bits = (self.max_rs_entries - 1).bit_length()
        self.start_pc = cfg.start_pc

        self._toolchain_isa_str = gen_isa_string(extensions, cfg.xlen, skip_internal=True)
