from typing import AbstractSet

from amaranth import Value
from amaranth.lib.data import StructLayout

from coreblocks.arch.isa_consts import SatpModeEncoding

__all__ = [
    "VirtualMemoryParams",
]


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

    def __init__(
        self,
        *,
        xlen: int,
        supervisor_mode: bool = False,
        asidlen: int = 0,
        supported_schemes: AbstractSet[SatpModeEncoding] = frozenset({SatpModeEncoding.BARE}),
    ):
        self.supported_schemes = frozenset(supported_schemes)

        if SatpModeEncoding.BARE not in self.supported_schemes:
            raise ValueError("Supported virtual memory schemes must include BARE")

        if not supervisor_mode and self.supported_schemes != {SatpModeEncoding.BARE}:
            raise ValueError("Virtual memory schemes other than BARE require supervisor mode support")

        if asidlen < 0:
            raise ValueError(f"ASIDLEN must be non-negative, got {asidlen}")

        self.satp_layout = SatpLayout(xlen)

        max_asidlen = self.satp_layout["asid"].width
        if asidlen > max_asidlen:
            raise ValueError(f"ASIDLEN={asidlen} exceeds maximum {max_asidlen} for XLEN={xlen}")

        supported_for_xlen = SatpModeEncoding.valid_modes(xlen)
        if not self.supported_schemes <= supported_for_xlen:
            raise ValueError(f"Schemes {self.supported_schemes - supported_for_xlen} are not valid for XLEN={xlen}")

        self.xlen = xlen
        self.asidlen = asidlen
        self.max_asid = (1 << asidlen) - 1
