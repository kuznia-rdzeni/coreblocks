from __future__ import annotations

from amaranth.utils import exact_log2

from coreblocks.arch.isa import ISA, gen_isa_string
from .icache_params import ICacheParameters
from .fu_params import extensions_supported
from ..peripherals.wishbone import WishboneParameters
from transactron.utils import DependentCache

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .configurations import CoreConfiguration

__all__ = ["GenParams"]


class GenParams(DependentCache):
    def __init__(self, cfg: CoreConfiguration):
        super().__init__()

        self.func_units_config = cfg.func_units_config

        ext_partial, ext_full = extensions_supported(self.func_units_config, cfg.embedded, cfg.compressed)
        extensions = ext_partial if cfg.allow_partial_extensions else ext_full
        if not cfg.allow_partial_extensions and ext_partial != ext_full:
            raise RuntimeError(f"Extensions {ext_partial & ~ext_full!r} are only partially supported")

        extensions |= cfg._implied_extensions
        self.isa_str = gen_isa_string(extensions, cfg.xlen)

        self.isa = ISA(self.isa_str)

        self.pma = cfg.pma

        bytes_in_word = self.isa.xlen // 8
        bytes_in_word_log = exact_log2(bytes_in_word)
        self.wb_params = WishboneParameters(data_width=self.isa.xlen, addr_width=self.isa.xlen - bytes_in_word_log)

        self.icache_params = ICacheParameters(
            addr_width=self.isa.xlen,
            word_width=self.isa.xlen,
            fetch_block_bytes_log=cfg.fetch_block_bytes_log,
            num_of_ways=cfg.icache_ways,
            num_of_sets_bits=cfg.icache_sets_bits,
            line_bytes_log=cfg.icache_line_bytes_log,
            enable=cfg.icache_enable,
        )

        self.debug_signals_enabled = cfg.debug_signals

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

        self.ftq_size_log = cfg.ftq_size_log
        self.ftq_size = 2**self.ftq_size_log

        self.min_instr_width_bytes = 2 if cfg.compressed else 4
        self.min_instr_width_bytes_log = exact_log2(self.min_instr_width_bytes)

        self.fetch_block_bytes_log = cfg.fetch_block_bytes_log
        if self.fetch_block_bytes_log < bytes_in_word_log:
            raise ValueError("Fetch block must be not smaller than the machine word.")
        self.fetch_block_bytes = 2**self.fetch_block_bytes_log
        self.fetch_width = 2**cfg.fetch_block_bytes_log // self.min_instr_width_bytes
        self.fetch_width_log = exact_log2(self.fetch_width)

        self.bpu_stages_cnt = 1
        self.bpu_meta_len = 1
        self.global_branch_history_len = cfg.bpu_global_history_len

        self.instr_buffer_size = cfg.instr_buffer_size
        self.extra_verification = cfg.extra_verification

        self.interrupt_custom_count = cfg.interrupt_custom_count
        self.interrupt_custom_edge_trig_mask = cfg.interrupt_custom_edge_trig_mask

        self._toolchain_isa_str = gen_isa_string(extensions, cfg.xlen, skip_internal=True)

        self._generate_test_hardware = cfg._generate_test_hardware

        self.marchid = cfg.marchid
        self.mimpid = cfg.mimpid
