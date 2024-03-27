from amaranth import *
from typing import Iterable

from coreblocks.interface.layouts import CSRLayouts
from coreblocks.params.genparams import GenParams
from coreblocks.priv.csr.csr_register import CSRRegister
from transactron.core.method import Method
from transactron.core.sugar import def_method
from transactron.core.tmodule import TModule


class AliasedCSR(CSRRegister):
    def __init__(self, gen_params: GenParams, fields: Iterable[tuple[int, CSRRegister]]):
        self.gen_params = gen_params
        self.width = 32
        self.fields = fields
        csr_layouts = gen_params.get(CSRLayouts)
        self._fu_read = Method(o=csr_layouts._fu_read)
        self._fu_write = Method(i=csr_layouts._fu_write)

        # verify interleaving and virtual
        # oh.... for csr may not be virtual - access from both float
        # register it

        # TODO: Warl mode

    def elaboratable(self, platform):
        m = TModule()

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
