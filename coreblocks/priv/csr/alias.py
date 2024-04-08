from amaranth import *
from typing import Optional

from coreblocks.interface.layouts import CSRRegisterLayouts
from coreblocks.params.genparams import GenParams
from coreblocks.priv.csr.csr_register import CSRRegister
from coreblocks.func_blocks.csr.csr import CSRListKey
from transactron.core.method import Method
from transactron.core.sugar import def_method
from transactron.core.tmodule import TModule
from transactron.utils.dependencies import DependencyManager


class AliasedCSR(Elaboratable):  # todo csr protocol ??
    def __init__(self, csr_number: Optional[int], gen_params: GenParams, width: Optional[int] = None):
        self.gen_params = gen_params
        self.csr_number = csr_number
        self.width = width if width is not None else gen_params.isa.xlen
        self.fields = []
        csr_layouts = gen_params.get(CSRRegisterLayouts)

        self._fu_read = Method(o=csr_layouts._fu_read)
        self._fu_write = Method(i=csr_layouts._fu_write)

        self.elaborated = False

        # append to global CSR list
        if csr_number is not None:
            dm = gen_params.get(DependencyManager)
            dm.add_dependency(CSRListKey(), self)

        # TODO: Warl mode

    def add_field(self, bit_position: int, csr: CSRRegister):
        assert not self.elaborated
        self.fields.append((bit_position, csr))
        # verify interleaving and virtual
        # oh.... for csr may not be virtual - access from both float
        # check if fits in width

    def elaborate(self, platform):
        m = TModule()
        self.elaborated = True

        @def_method(m, self._fu_write)
        def _(data: Value):
            for start, csr in self.fields:
                csr._fu_write(m, data.bit_select(start, csr.width))

        @def_method(m, self._fu_read)
        def _():
            data = Signal(self.width)
            for start, csr in self.fields:
                m.d.comb += data.bit_select(start, csr.width).eq(csr._fu_read(m))

        return m
