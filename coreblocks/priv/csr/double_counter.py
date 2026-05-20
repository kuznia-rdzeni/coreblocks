from amaranth import *
from typing import Optional

from transactron.core import Method, TModule, def_method
from transactron.utils import get_src_loc

from coreblocks.arch import CSRAddress
from coreblocks.params.genparams import GenParams
from coreblocks.priv.csr.csr_register import CSRRegister
from coreblocks.priv.csr.shadow import ShadowCSR

__all__ = ["DoubleCounterCSR"]


class DoubleCounterCSR(Elaboratable):
    """DoubleCounterCSR

    A 64-bit CSR counter, visible on two CSR addresses on RV32.

    Attributes
    ----------
    increment: Method
        Increments the counter by 1. At overflow, counter value is set to 0.
    """

    def __init__(
        self,
        gen_params: GenParams,
        low_addr: CSRAddress,
        high_addr: CSRAddress,
        shadow_low_addr: Optional[CSRAddress] = None,
        shadow_high_addr: Optional[CSRAddress] = None,
        shadow_access_filter=None,
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
        """
        assert (shadow_low_addr is None) == (shadow_high_addr is None)

        self.gen_params = gen_params

        self.increment = Method()

        self.register = CSRRegister(None, gen_params, width=64)

        self.register_low = ShadowCSR(low_addr, gen_params, self.register, width=gen_params.isa.xlen)
        self.register_high = (
            ShadowCSR(high_addr, gen_params, self.register, width=gen_params.isa.xlen, offset=gen_params.isa.xlen)
            if gen_params.isa.xlen == 32
            else None
        )

        self.shadow_low = self.shadow_high = None
        if shadow_low_addr is not None:
            self.shadow_low = ShadowCSR(
                shadow_low_addr,
                gen_params,
                self.register_low,
                write_mask=0,
                access_filter=shadow_access_filter,
                src_loc=get_src_loc(1),
            )
            if self.register_high is not None:
                self.shadow_high = ShadowCSR(
                    shadow_high_addr,
                    gen_params,
                    self.register_high,
                    write_mask=0,
                    access_filter=shadow_access_filter,
                    src_loc=get_src_loc(1),
                )

    def elaborate(self, platform):
        m = TModule()

        m.submodules.register = self.register
        m.submodules.register_low = self.register_low
        if self.register_high is not None:
            m.submodules.register_high = self.register_high

        @def_method(m, self.increment)
        def _():
            register_read = self.register.read(m).data
            self.register.write(m, data=register_read + 1)

        if self.shadow_low is not None:
            m.submodules.shadow_low = self.shadow_low

        if self.shadow_high is not None:
            m.submodules.shadow_high = self.shadow_high

        return m
