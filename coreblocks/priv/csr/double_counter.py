from collections.abc import Callable
from typing import Optional
from amaranth import *
from amaranth_types import ValueLike

from transactron.core import Method, TModule, def_method

from coreblocks.arch import CSRAddress
from coreblocks.params.genparams import GenParams
from coreblocks.priv.csr.csr_register import CSRRegister
from coreblocks.priv.csr.double_shadow import DoubleShadowCSR

__all__ = ["DoubleCounterCSR"]


class DoubleCounterCSR(Elaboratable):
    """Double counter CSR.

    A 64-bit CSR counter, visible on two CSR addresses on RV32.
    """

    increment: Method
    """Increments the counter by 1. At overflow, counter value is set to 0."""

    def __init__(
        self,
        gen_params: GenParams,
        low_addr: Optional[CSRAddress] = None,
        high_addr: Optional[CSRAddress] = None,
        shadow_low_addr: Optional[CSRAddress] = None,
        shadow_high_addr: Optional[CSRAddress] = None,
        shadow_access_filter: Optional[Callable[[TModule, Value], ValueLike]] = None,
        read_only_zero: bool = False,
    ):
        """
        Parameters
        ----------
        gen_params: GenParams
            Core generation parameters.
        low_addr: CSRAddress
            Address of the CSR register representing lower part of the counter on RV32, or the entire counter on RV64.
        high_addr: CSRAddress
            Address of the CSR register representing higher part of the counter on RV32. Unused on RV64.
        shadow_low_addr: CSRAddress, optional
            Address of the shadow CSR register for the lower part of the counter. If provided, shadow CSR is
            synthetised with read-only access to the counter value.
        shadow_high_addr: CSRAddress, optional
            Address of the shadow CSR register for the higher part of the counter. If provided, shadow CSR is
            synthetised with read-only access to the counter value. If `shadow_low_addr` is provided,
            `shadow_high_addr` also should be provided.
        shadow_access_filter: Callable, optional
            Provides `access_filter` for additional shadow CSRs.
        read_only_zero: bool
            If True, the increment is no-op and the counter always reads as zero.
        """
        self.increment = Method()
        self.register = CSRRegister(None, gen_params, width=64, ro_bits=~0 if read_only_zero else 0)
        self.shadow = DoubleShadowCSR(
            gen_params, self.register, low_addr, high_addr, shadow_low_addr, shadow_high_addr, shadow_access_filter
        )

        self.read_only_zero = read_only_zero

    def elaborate(self, platform):
        m = TModule()

        m.submodules.register = self.register
        m.submodules.shadow = self.shadow

        @def_method(m, self.increment)
        def _():
            if self.read_only_zero:
                return

            register_read = self.register.read(m).data
            self.register.write(m, data=register_read + 1)

        return m
