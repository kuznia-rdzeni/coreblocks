from __future__ import annotations

from amaranth.utils import ceil_log2, exact_log2

from coreblocks.arch.isa import ISA, gen_isa_string
from .icache_params import ICacheParameters
from .vmem_params import VirtualMemoryParameters
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

        ext_partial, ext_full = extensions_supported(self.func_units_config, cfg.embedded, cfg.compressed, cfg.zcb)
        extensions = ext_partial if cfg.allow_partial_extensions else ext_full
        if not cfg.allow_partial_extensions and ext_partial != ext_full:
            raise RuntimeError(f"Extensions {ext_partial & ~ext_full!r} are only partially supported")

        extensions |= cfg._implied_extensions
        self.isa_str = gen_isa_string(extensions, cfg.xlen)

        self.isa = ISA(self.isa_str)

        self.pma = cfg.pma

        bytes_in_word = self.isa.xlen // 8
        bytes_in_word_log = exact_log2(bytes_in_word)

        max_phys_addr_bits = VirtualMemoryParameters.max_physical_address_bits(cfg.xlen, cfg.supported_vm_schemes)
        self.phys_addr_bits = cfg.phys_addr_bits if cfg.phys_addr_bits is not None else max_phys_addr_bits
        if self.phys_addr_bits < bytes_in_word_log:
            raise ValueError(
                f"Physical address width ({self.phys_addr_bits}) " f"must be at least {bytes_in_word_log} bits"
            )
        if self.phys_addr_bits > max_phys_addr_bits:
            raise ValueError(
                "Physical address width "
                f"({self.phys_addr_bits}) exceeds maximum {max_phys_addr_bits} "
                f"bits for XLEN={cfg.xlen}"
            )

        self.wb_params = WishboneParameters(
            data_width=self.isa.xlen,
            addr_width=self.phys_addr_bits - bytes_in_word_log,
        )

        self.vmem_params = VirtualMemoryParameters(
            xlen=cfg.xlen,
            supervisor_mode=cfg.supervisor_mode,
            asidlen=cfg.asidlen,
            supported_schemes=cfg.supported_vm_schemes,
        )

        self.icache_params = ICacheParameters(
            addr_width=self.phys_addr_bits,
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
        #     raise Exception(f"Functional unit configuration do not support all extension required by{isa_str}")

        self.max_rs_entries = 1

        for block in self.func_units_config:
            self.max_rs_entries = max(self.max_rs_entries, block.get_rs_entry_count())

        self.rs_number_bits = ceil_log2(len(self.func_units_config))

        self.phys_regs = 2**cfg.phys_regs_bits
        self.rob_entries = 2**cfg.rob_entries_bits

        self.phys_regs_bits = cfg.phys_regs_bits
        self.rob_entries_bits = cfg.rob_entries_bits
        self.max_rs_entries_bits = ceil_log2(self.max_rs_entries)
        self.start_pc = cfg.start_pc

        self.frontend_superscalarity = cfg.frontend_superscalarity
        self.announcement_superscalarity = cfg.announcement_superscalarity
        self.retirement_superscalarity = cfg.retirement_superscalarity
        max_superscalarity = max(self.frontend_superscalarity, self.retirement_superscalarity)
        if max_superscalarity & (max_superscalarity - 1) != 0:
            raise ValueError("Maximum of frontend and retirement superscalarity must be a power of 2")

        self.checkpoint_count = cfg.checkpoint_count
        self.tag_bits = cfg.tag_bits
        assert cfg.checkpoint_count < 2**cfg.tag_bits

        self.min_instr_width_bytes = 2 if cfg.compressed or cfg.zcb else 4
        self.min_instr_width_bytes_log = exact_log2(self.min_instr_width_bytes)

        self.fetch_block_bytes_log = cfg.fetch_block_bytes_log
        if self.fetch_block_bytes_log < bytes_in_word_log:
            raise ValueError("Fetch block must be not smaller than the machine word.")
        self.fetch_block_bytes = 2**self.fetch_block_bytes_log
        self.fetch_width = 2**cfg.fetch_block_bytes_log // self.min_instr_width_bytes
        self.fetch_width_log = exact_log2(self.fetch_width)

        self.instr_buffer_size = cfg.instr_buffer_size
        self.extra_verification = cfg.extra_verification

        self.interrupt_custom_count = cfg.interrupt_custom_count
        self.interrupt_custom_edge_trig_mask = cfg.interrupt_custom_edge_trig_mask

        self.user_mode = cfg.user_mode
        self.supervisor_mode = cfg.supervisor_mode
        self.hpm_counters_count = cfg.hpm_counters_count

        self.tlb_config = cfg.tlb_config

        for name, tlb_cfg in (
            ("itlb", self.tlb_config.itlb),
            ("dtlb", self.tlb_config.dtlb),
            ("l2tlb", self.tlb_config.l2tlb),
        ):
            if tlb_cfg.entries <= 0:
                raise ValueError(f"{name} entries must be positive")
            if tlb_cfg.ways <= 0:
                raise ValueError(f"{name} ways must be positive")
            if tlb_cfg.entries % tlb_cfg.ways != 0:
                raise ValueError(f"{name} entries must be divisible by ways")

        if self.hpm_counters_count < 0 or self.hpm_counters_count > 29:
            raise ValueError("HPM counters count must be in range [0, 29]")

        # TODO: remove when HPM counters are implemented
        if self.hpm_counters_count > 0:
            raise NotImplementedError("HPM counters are currently not implemented")

        if self.supervisor_mode and not self.user_mode:
            raise ValueError("Supervisor mode support requires user mode support")

        self.pmp_register_count = cfg.pmp_register_count
        if self.pmp_register_count not in [0, 16, 64]:
            raise ValueError("PMP register count must be 0, 16, or 64")

        if cfg.pmp_grain_log < 2:
            raise ValueError("pmp_grain_log must be >= 2 (minimum 4-byte granularity)")

        self.pmp_grain = cfg.pmp_grain_log - 2  # G parameter from RISC-V spec
        self.pmp_grain_bytes = 2**cfg.pmp_grain_log
        if self.pmp_register_count > 0 and self.icache_params.enable:
            if self.pmp_grain_bytes < self.icache_params.line_size_bytes:
                raise ValueError("PMP grain size must be >= cache line size")

        self._toolchain_isa_str = gen_isa_string(extensions, cfg.xlen, skip_internal=True)

        self._generate_test_hardware = cfg._generate_test_hardware

        self.marchid = cfg.marchid
        self.mimpid = cfg.mimpid

        self.multiport_memory_type = cfg.multiport_memory_type
