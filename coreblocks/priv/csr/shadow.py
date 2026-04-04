from typing import Optional

from amaranth import *
from transactron.core.method import Method
from transactron.core.sugar import def_method
from transactron.core.tmodule import TModule
from transactron.utils.dependencies import DependencyContext

from coreblocks.func_blocks.csr.csr import CSRListKey
from coreblocks.interface.layouts import CSRRegisterLayouts
from coreblocks.params.genparams import GenParams
from coreblocks.priv.csr.csr_register import CSRRegister


class ShadowCSR(CSRRegister):  # TODO: CSR register protocol
    """CSR shadow register.

    Exposes an instruction-visible CSR number that reads/writes another CSR.
    Optional bit masks can restrict visible read bits and writable bits.
    """

    def __init__(
        self,
        csr_number: Optional[int],
        gen_params: GenParams,
        shadowed: CSRRegister,
        *,
        mask: Optional[int] = None,
        read_mask: Optional[int] = None,
        write_mask: Optional[int] = None,
    ):
        if mask is not None:
            assert (
                read_mask is None and write_mask is None
            ), "Cannot specify both full mask and separate read/write masks"
            read_mask = write_mask = mask

        self.gen_params = gen_params
        self.csr_number = csr_number
        self.shadowed = shadowed
        self.width = shadowed.width

        full_mask = (1 << self.width) - 1
        self.read_mask: int = full_mask if read_mask is None else read_mask
        self.write_mask: int = full_mask if write_mask is None else write_mask

        if self.read_mask > full_mask or self.write_mask > full_mask:
            raise ValueError("Masks cannot have bits outside of CSR width")

        csr_layouts = gen_params.get(CSRRegisterLayouts)
        self._fu_read = Method(o=csr_layouts._fu_read)
        self._fu_write = Method(i=csr_layouts._fu_write)
        self.value = Signal(self.width)

        self.read = Method(o=csr_layouts.read)
        self.read_comb = Method(o=csr_layouts.read)
        self.write = Method(i=csr_layouts.write)

        if csr_number is not None:
            DependencyContext.get().add_dependency(CSRListKey(), self)

    def elaborate(self, platform):
        m = TModule()

        @def_method(m, self._fu_write)
        def _(data: Value):
            return self.shadowed._fu_write(
                m,
                data=(data & self.write_mask) | (self.shadowed.read(m).data & ~self.write_mask),
            )

        @def_method(m, self._fu_read)
        def _() -> Value:
            m.d.top_comb += self.value.eq(self.shadowed._fu_read(m).data & self.read_mask)
            return self.value

        @def_method(m, self.write)
        def _(data: Value):
            self.shadowed.write(
                m,
                data=(data & self.write_mask) | (self.shadowed.read(m).data & ~self.write_mask),
            )

        @def_method(m, self.read, nonexclusive=True)
        def _():
            data = self.shadowed.read(m)
            return {
                "data": data.data & self.read_mask,
                "read": data.read,
                "written": data.written,
            }

        @def_method(m, self.read_comb, nonexclusive=True)
        def _():
            data = self.shadowed.read_comb(m)
            return {
                "data": data.data & self.read_mask,
                "read": data.read,
                "written": data.written,
            }

        return m
