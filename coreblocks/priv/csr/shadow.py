from typing import Optional, Callable

from amaranth import *
from amaranth import ValueLike
from amaranth_types import SrcLoc
from transactron.core.method import Method
from transactron.core.transaction import Transaction
from transactron.core.sugar import def_method
from transactron.core.tmodule import TModule
from transactron.utils import get_src_loc
from transactron.lib import logging

from coreblocks.params.genparams import GenParams
from coreblocks.priv.csr.csr_register import CSRRegisterBase

__all__ = ["ShadowCSR"]


log = logging.HardwareLogger("priv.csr.shadow")


class ShadowCSR(CSRRegisterBase):
    """CSR shadow register.

    Exposes an instruction-visible CSR number that reads/writes another CSR.
    Optional bit masks can restrict visible read bits and writable bits for both instruction-visible access and
    internal CSR logic.
    """

    def __init__(
        self,
        csr_number: Optional[int],
        gen_params: GenParams,
        shadowed: CSRRegisterBase,
        *,
        mask: Optional[ValueLike | Method] = None,
        read_mask: Optional[ValueLike | Method] = None,
        write_mask: Optional[ValueLike | Method] = None,
        access_filter: Optional[Callable[[TModule, Value], ValueLike]] = None,
        src_loc: int | SrcLoc = 0,
    ):
        super().__init__(gen_params, csr_number, width=shadowed.width, src_loc=get_src_loc(src_loc))

        if mask is not None:
            assert (
                read_mask is None and write_mask is None
            ), "Cannot specify both full mask and separate read/write masks"
            read_mask = write_mask = mask

        self.shadowed = shadowed

        full_mask = (1 << self.width) - 1
        self.read_mask: ValueLike | Method = full_mask if read_mask is None else read_mask
        self.write_mask: ValueLike | Method = full_mask if write_mask is None else write_mask
        self.access_filter = access_filter if access_filter is not None else (lambda _, __: C(1))

    def elaborate(self, platform):
        m = TModule()

        write_mask = Signal.like(self.value)
        read_mask = Signal.like(self.value)

        if isinstance(self.write_mask, Method):
            with Transaction().body(m) as t:
                m.d.comb += write_mask.eq(self.write_mask(m).data)
            log.error(m, ~t.run, "assert transaction running failed")
        else:
            m.d.comb += write_mask.eq(self.write_mask)

        if isinstance(self.read_mask, Method):
            with Transaction().body(m) as t:
                m.d.comb += read_mask.eq(self.read_mask(m).data)
            log.error(m, ~t.run, "assert transaction running failed")
        else:
            m.d.comb += read_mask.eq(self.read_mask)

        m.d.comb += self.value.eq(self.shadowed.value & read_mask)

        @def_method(m, self._fu_write)
        def _(data: Value):
            return self.shadowed._fu_write(
                m,
                data=(data & write_mask) | (self.shadowed.read(m).data & ~write_mask),
            )

        @def_method(m, self._fu_read)
        def _() -> Value:
            return self.shadowed._fu_read(m).data & read_mask

        @def_method(m, self.write)
        def _(data: Value):
            self.shadowed.write(
                m,
                data=(data & write_mask) | (self.shadowed.read(m).data & ~write_mask),
            )

        @def_method(m, self.read, nonexclusive=True)
        def _():
            result = self.shadowed.read(m)
            return {
                "data": result.data & read_mask,
                "read": result.read,
                "written": result.written,
            }

        @def_method(m, self.read_comb, nonexclusive=True)
        def _():
            result = self.shadowed.read_comb(m)
            return {
                "data": result.data & read_mask,
                "read": result.read,
                "written": result.written,
            }

        @def_method(m, self._fu_access_valid)
        def _(priv_mode):
            return {"valid": self.access_filter(m, priv_mode) & self.shadowed._fu_access_valid(m, priv_mode).valid}

        return m
