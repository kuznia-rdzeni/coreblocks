from amaranth import *
from typing import Optional

from transactron.core import Method, TModule, def_method

from coreblocks.arch import CSRAddress
from coreblocks.params.genparams import GenParams
from coreblocks.priv.csr.csr_register import CSRRegister
from coreblocks.priv.csr.shadow import ShadowCSR

__all__ = ["DoubleCounterCSR"]


class DoubleCounterCSR(Elaboratable):
    """DoubleCounterCSR
    Groups two `CSRRegisters` to form counter with double `isa.xlen` width.

    Attributes
    ----------
    increment: Method
        Increments the counter by 1. At overflow, counter value is set to 0.
    """

    def __init__(
        self,
        gen_params: GenParams,
        low_addr: CSRAddress,
        high_addr: Optional[CSRAddress] = None,
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
            Address of the CSR register representing lower part of the counter (bits `[isa.xlen-1 : 0]`).
        high_addr: CSRAddress or None, optional
            Address of the CSR register representing higher part of the counter (bits `[2*isa.xlen-1 : isa.xlen]`).
            If high_addr is None or not provided, then higher CSR is not synthetised and only the width of
            low_addr CSR is available to the counter.
        shadow_low_addr: CSRAddress or None, optional
            Address of the shadow CSR register for the lower part of the counter. If provided, shadow CSR is
            synthetised with read-only access to the counter value.
        shadow_high_addr: CSRAddress or None, optional
            Address of the shadow CSR register for the higher part of the counter. If provided, shadow CSR is
            synthetised with read-only access to the counter value. If high_addr is None, providing shadow_high_addr
            will raise an error.
        """
        self.gen_params = gen_params

        self.increment = Method()

        self.register_low = CSRRegister(low_addr, gen_params)
        self.register_high = CSRRegister(high_addr, gen_params) if high_addr is not None else None

        self.shadow_low = self.shadow_high = None
        if shadow_low_addr is not None:
            self.shadow_low = ShadowCSR(
                shadow_low_addr,
                gen_params,
                self.register_low,
                write_mask=0,
                access_filter=shadow_access_filter,
            )
        if shadow_high_addr is not None:
            if not self.register_high:
                raise ValueError("shadow_high_addr provided but high_addr is None")

            if not shadow_low_addr:
                raise ValueError("shadow_high_addr provided but shadow_low_addr is None")

            self.shadow_high = ShadowCSR(
                shadow_high_addr,
                gen_params,
                self.register_high,
                write_mask=0,
                access_filter=shadow_access_filter,
            )

    def elaborate(self, platform):
        m = TModule()

        m.submodules.register_low = self.register_low
        if self.register_high is not None:
            m.submodules.register_high = self.register_high

        @def_method(m, self.increment)
        def _():
            register_read = self.register_low.read(m).data
            self.register_low.write(m, data=register_read + 1)

            if self.register_high is not None:
                with m.If(register_read == (1 << self.gen_params.isa.xlen) - 1):
                    self.register_high.write(m, data=self.register_high.read(m).data + 1)

        if self.shadow_low is not None:
            m.submodules.shadow_low = self.shadow_low

        if self.shadow_high is not None:
            m.submodules.shadow_high = self.shadow_high

        return m
