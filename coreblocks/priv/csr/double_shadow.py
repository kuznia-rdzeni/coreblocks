from collections.abc import Callable
from typing import Optional
from amaranth import *
from amaranth_types import ValueLike

from transactron.core import Method, TModule
from transactron.utils import get_src_loc

from coreblocks.arch import CSRAddress
from coreblocks.params.genparams import GenParams
from coreblocks.priv.csr.csr_register import CSRRegisterBase
from coreblocks.priv.csr.shadow import ShadowCSR

__all__ = ["DoubleShadowCSR"]


class DoubleShadowCSR(Elaboratable):
    """Double shadow CSR.

    Creates two 32-bit shadows of an 64-bit CSR on RV32, or a single 64-bit shadow on RV64.
    Can also create an additional shadow pair, e.g. for S-mode registers.
    """

    def __init__(
        self,
        gen_params: GenParams,
        shadowed: CSRRegisterBase,
        low_addr: Optional[CSRAddress] = None,
        high_addr: Optional[CSRAddress] = None,
        shadow_low_addr: Optional[CSRAddress] = None,
        shadow_high_addr: Optional[CSRAddress] = None,
        shadow_access_filter: Optional[Callable[[TModule, Value], ValueLike]] = None,
    ):
        """
        Parameters
        ----------
        gen_params: GenParams
            Core generation parameters.
        low_addr: CSRAddress, optional
            Address of the CSR register representing lower part of the CSR on RV32, or the entire CSR on RV64.
        high_addr: CSRAddress, optional
            Address of the CSR register representing higher part of the CSR on RV32. Unused on RV64.
        shadow_low_addr: CSRAddress, optional
            Address of the shadow CSR register for the lower part of the CSR. If provided, shadow CSR is
            synthetised with read-only access to the CSR value.
        shadow_high_addr: CSRAddress, optional
            Address of the shadow CSR register for the higher part of the CSR. If provided, shadow CSR is
            synthetised with read-only access to the CSR value. If `shadow_low_addr` is provided,
            `shadow_high_addr` also should be provided.
        shadow_access_filter: Callable, optional
            Provides `access_filter` for additional shadow CSRs.
        """
        assert (low_addr is None) == (high_addr is None)
        assert (shadow_low_addr is None) == (shadow_high_addr is None)

        self.gen_params = gen_params

        self.increment = Method()

        self.register_low = ShadowCSR(low_addr, gen_params, shadowed, width=gen_params.isa.xlen)
        self.register_high = (
            ShadowCSR(high_addr, gen_params, shadowed, width=gen_params.isa.xlen, offset=gen_params.isa.xlen)
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

        m.submodules.register_low = self.register_low
        if self.register_high is not None:
            m.submodules.register_high = self.register_high

        if self.shadow_low is not None:
            m.submodules.shadow_low = self.shadow_low

        if self.shadow_high is not None:
            m.submodules.shadow_high = self.shadow_high

        return m
