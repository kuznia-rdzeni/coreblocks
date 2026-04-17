from typing import Collection

from coreblocks.arch.isa_consts import SatpMode, SatpLayout


class VirtualMemoryParameters:
    """Parameters for virtual memory support."""

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

        self.xlen = xlen
        self.asidlen = asidlen
        self.max_asid = (1 << asidlen) - 1
