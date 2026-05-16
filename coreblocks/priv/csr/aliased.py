from amaranth import *
from amaranth_types import SrcLoc

from typing import Optional
from enum import Enum

from coreblocks.params.genparams import GenParams
from coreblocks.priv.csr.csr_register import CSRRegister, CSRRegisterBase

from transactron.core.sugar import def_method
from transactron.core.tmodule import TModule
from transactron.utils import get_src_loc


class AliasedCSR(CSRRegisterBase):
    def __init__(
        self,
        csr_number: Optional[int],
        gen_params: GenParams,
        width: Optional[int] = None,
        src_loc: int | SrcLoc = 0,
    ):
        if width is None:
            width = gen_params.isa.xlen

        super().__init__(gen_params, csr_number, width, get_src_loc(src_loc))

        self.fields: list[tuple[int, CSRRegisterBase]] = []
        self.ro_values: list[tuple[int, int, int | Enum]] = []

        self.elaborated = False

        # TODO: WPRI defult mode

    def add_field(self, bit_position: int, csr: CSRRegister):
        assert not self.elaborated
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
        def _(data: Value, op_type: Value):
            for start, csr in self.fields:
                csr._fu_write(m, data=data[start : start + csr.width], op_type=op_type)

        @def_method(m, self._fu_read)
        def _() -> Value:
            for start, csr in self.fields:
                m.d.av_comb += self.value[start : start + csr.width].eq(csr._fu_read(m).data)

            for start, width, value in self.ro_values:
                m.d.av_comb += self.value[start : start + width].eq(value)

            return self.value

        @def_method(m, self.write)
        def _(data: Value):
            for start, csr in self.fields:
                csr.write(m, data[start : start + csr.width])

        def read_def(fn):
            read_data = Signal.like(self.value)
            any_read = 0
            any_written = 0

            for start, csr in self.fields:
                result = fn(m, csr)
                m.d.av_comb += read_data[start : start + csr.width].eq(result.data)
                any_read |= result.read
                any_written |= result.written

            for start, width, value in self.ro_values:
                m.d.av_comb += read_data[start : start + width].eq(value)

            return {"data": read_data, "read": any_read, "written": any_written}

        @def_method(m, self.read, nonexclusive=True)
        def _():
            return read_def(lambda m, csr: csr.read(m))

        @def_method(m, self.read_comb, nonexclusive=True)
        def _():
            return read_def(lambda m, csr: csr.read_comb(m))

        @def_method(m, self._fu_access_valid)
        def _(priv_mode):
            valid = 1
            for _, csr in self.fields:
                valid &= csr._fu_access_valid(m, priv_mode).valid

            return {"valid": valid}

        return m
