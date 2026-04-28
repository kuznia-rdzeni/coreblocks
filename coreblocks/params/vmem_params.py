from dataclasses import dataclass, field
from typing import Collection

from coreblocks.arch.isa_consts import SatpMode, SatpLayout, PAGE_SIZE_LOG

__all__ = [
    "TLBLineConfiguration",
    "TLBCacheConfiguration",
    "VirtualMemoryParameters",
]


@dataclass(frozen=True)
class TLBLineConfiguration:
    entries: int = 16
    ways: int = 4


@dataclass(frozen=True)
class TLBCacheConfiguration:
    itlb: TLBLineConfiguration = field(default_factory=TLBLineConfiguration)
    dtlb: TLBLineConfiguration = field(default_factory=TLBLineConfiguration)
    l2tlb: TLBLineConfiguration = field(default_factory=lambda: TLBLineConfiguration(entries=64, ways=8))


class VirtualMemoryParameters:
    """Parameters for virtual memory support."""

    @staticmethod
    def max_physical_address_bits(xlen: int, supported_schemes: Collection[SatpMode]) -> int:
        if xlen == 32 and supported_schemes == {SatpMode.BARE}:
            return 32  # without virtual memory only lower 32 bits of physical addresses are reachable

        satp_layout = SatpLayout(xlen)
        return satp_layout["ppn"].width + PAGE_SIZE_LOG

    @staticmethod
    def vpn_bits_for_mode(xlen: int, mode: SatpMode) -> int:
        return SatpMode.bits_per_page_table_level(xlen) * SatpMode.level_count(mode)

    @staticmethod
    def size_class_shift(xlen: int, size_class: int) -> int:
        return SatpMode.bits_per_page_table_level(xlen) * size_class

    def __init__(
        self,
        *,
        xlen: int,
        supervisor_mode: bool = False,
        asidlen: int = 0,
        supported_schemes: Collection[SatpMode] = (SatpMode.BARE,),
    ):
        self.supported_schemes = frozenset(supported_schemes)

        if SatpMode.BARE not in self.supported_schemes:
            raise ValueError("Supported virtual memory schemes must include BARE")

        if not supervisor_mode and self.supported_schemes != {SatpMode.BARE}:
            raise ValueError("Virtual memory schemes other than BARE require supervisor mode support")

        if asidlen < 0:
            raise ValueError(f"ASIDLEN must be non-negative, got {asidlen}")

        self.satp_layout = SatpLayout(xlen)

        max_asidlen = self.satp_layout["asid"].width
        if asidlen > max_asidlen:
            raise ValueError(f"ASIDLEN={asidlen} exceeds maximum {max_asidlen} for XLEN={xlen}")

        supported_for_xlen = SatpMode.valid_modes(xlen)
        if not self.supported_schemes <= supported_for_xlen:
            raise ValueError(f"Schemes {self.supported_schemes - supported_for_xlen} are not valid for XLEN={xlen}")

        for mode in self.supported_schemes:
            dependencies = SatpMode.mode_dependencies(mode)
            if not dependencies <= self.supported_schemes:
                raise ValueError(
                    f"Schemes {dependencies - self.supported_schemes} are required by {mode} but not supported"
                )

        self.xlen = xlen
        self.asidlen = asidlen
        self.max_asid = (1 << asidlen) - 1
        self.page_table_level_bits = SatpMode.bits_per_page_table_level(xlen)
        self.max_tlb_vpn_bits = max(
            (self.vpn_bits_for_mode(xlen, mode) for mode in self.supported_non_bare_schemes),
            default=0,
        )
        self.max_tlb_size_class = max(
            (SatpMode.level_count(mode) - 1 for mode in self.supported_non_bare_schemes),
            default=0,
        )
        self.tlb_size_class_bits = self.max_tlb_size_class.bit_length()

    @property
    def supported_non_bare_schemes(self) -> Collection[SatpMode]:
        return [scheme for scheme in self.supported_schemes if scheme != SatpMode.BARE]
