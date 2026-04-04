from enum import IntFlag, auto, unique

from amaranth import Value
from amaranth.lib.data import StructLayout

from coreblocks.arch.isa_consts import SatpModeEncoding

__all__ = [
    "VirtualMemoryScheme",
    "VirtualMemoryParams",
]


@unique
class VirtualMemoryScheme(IntFlag):
    """
    RISC-V virtual memory schemes as defined in the privileged architecture specification.
    """

    BARE = auto()
    SV32 = auto()
    SV39 = auto()
    SV48 = auto()
    SV57 = auto()
    SV64 = auto()

    def get_encoding(self) -> SatpModeEncoding:
        """
        Get the encoding of this scheme for the SATP register.
        Only accepts single bit values.
        """

        if self.value.bit_count() != 1:
            raise ValueError("get_encoding only accepts single scheme, got multiple")

        match self:
            case VirtualMemoryScheme.BARE:
                return SatpModeEncoding.BARE
            case VirtualMemoryScheme.SV32:
                return SatpModeEncoding.SV32
            case VirtualMemoryScheme.SV39:
                return SatpModeEncoding.SV39
            case VirtualMemoryScheme.SV48:
                return SatpModeEncoding.SV48
            case VirtualMemoryScheme.SV57:
                return SatpModeEncoding.SV57
            case VirtualMemoryScheme.SV64:
                return SatpModeEncoding.SV64


class SatpLayout(StructLayout):
    ppn: Value
    asid: Value
    mode: Value

    def __init__(self, xlen: int):
        match xlen:
            case 32:
                super().__init__(
                    {
                        "ppn": 22,
                        "asid": 9,
                        "mode": 1,
                    }
                )
            case 64:
                super().__init__(
                    {
                        "ppn": 44,
                        "asid": 16,
                        "mode": 4,
                    }
                )
            case _:
                raise ValueError(f"Unsupported XLEN for SATP layout: {xlen}")


class VirtualMemoryParams:
    """Parameters for virtual memory support."""

    _XLEN_SCHEMES = {
        32: (VirtualMemoryScheme.BARE | VirtualMemoryScheme.SV32),
        64: (
            VirtualMemoryScheme.BARE
            | VirtualMemoryScheme.SV39
            | VirtualMemoryScheme.SV48
            | VirtualMemoryScheme.SV57
            | VirtualMemoryScheme.SV64
        ),
    }

    _XLEN_MAX_ASIDLEN = {
        32: 9,
        64: 16,
    }

    def __init__(
        self,
        *,
        xlen: int,
        supervisor_mode: bool = False,
        asidlen: int = 0,
        supported_schemes: VirtualMemoryScheme = VirtualMemoryScheme.BARE,
    ):
        if VirtualMemoryScheme.BARE not in supported_schemes:
            raise ValueError("Supported virtual memory schemes must include BARE")

        if not supervisor_mode and supported_schemes != VirtualMemoryScheme.BARE:
            raise ValueError("Virtual memory schemes other than BARE require supervisor mode support")

        if xlen not in self._XLEN_SCHEMES:
            raise ValueError(f"Unsupported XLEN for virtual memory parameters: {xlen}")

        if asidlen < 0:
            raise ValueError(f"ASIDLEN must be non-negative, got {asidlen}")

        max_asidlen = self._XLEN_MAX_ASIDLEN[xlen]
        if asidlen > max_asidlen:
            raise ValueError(f"ASIDLEN={asidlen} exceeds maximum {max_asidlen} for XLEN={xlen}")

        supported_for_xlen = self._XLEN_SCHEMES[xlen]
        if supported_schemes & ~supported_for_xlen:
            raise ValueError(f"Schemes {supported_schemes} are not valid for XLEN={xlen}")

        self.xlen = xlen
        self.asidlen = asidlen
        self.supported_schemes = supported_schemes

        self.max_asid = (1 << asidlen) - 1
        self.satp_layout = SatpLayout(xlen)
