from amaranth import *

from typing import Optional
from enum import Enum

from coreblocks.interface.layouts import CSRRegisterLayouts
from coreblocks.params.genparams import GenParams
from coreblocks.priv.csr.csr_register import CSRRegister
from coreblocks.func_blocks.csr.csr import CSRListKey
from transactron.core.method import Method
from transactron.core.sugar import def_method
from transactron.core.tmodule import TModule
from transactron.utils.dependencies import DependencyContext


class AliasedCSR(CSRRegister):  # TODO: CSR interface protocol
    """
    Temporary simple support for CSR aliasing for InternalInterruptController. Will be replaced with more complete
    implementation soon.
    """

    def __init__(self, csr_number: Optional[int], gen_params: GenParams, width: Optional[int] = None):
        self.gen_params = gen_params
        self.csr_number = csr_number
        self.width = width if width is not None else gen_params.isa.xlen

        self.fields: list[tuple[int, CSRRegister]] = []
        self.ro_values: list[tuple[int, int, int | Enum]] = []

        csr_layouts = gen_params.get(CSRRegisterLayouts)

        self._fu_read = Method(o=csr_layouts._fu_read)
        self._fu_write = Method(i=csr_layouts._fu_write)

        self.value = Signal(self.width)  # part of public CSR interface, useful for debugging

        self.elaborated = False

        # append to global CSR list
        if csr_number is not None:
            DependencyContext.get().add_dependency(CSRListKey(), self)

        # TODO: WPRI defult mode

    def add_field(self, bit_position: int, csr: CSRRegister):
        assert not self.elaborated
        assert csr.csr_number is None  # TODO: support for instruction accessible registers
        self.fields.append((bit_position, csr))
        # TODO: verify bounds

    def add_read_only_field(self, bit_position: int, bit_width: int, value: int | Enum):
        assert not self.elaborated
        self.ro_values.append((bit_position, bit_width, value))
        # TODO: verify bounds

    def elaborate(self, platform):
        m = TModule()
        self.elaborated = True

        @def_method(m, self._fu_write)
        def _(data: Value):
            for start, csr in self.fields:
                csr._fu_write(m, data[start : start + csr.width])

        @def_method(m, self._fu_read)
        def _() -> Value:
            for start, csr in self.fields:
                m.d.av_comb += self.value[start : start + csr.width].eq(csr._fu_read(m)["data"])

            for start, width, value in self.ro_values:
                m.d.av_comb += self.value[start : start + width].eq(value)

            return self.value

        return m
