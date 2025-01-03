from amaranth import *
from amaranth.lib.data import StructLayout
from amaranth.lib.enum import Enum

from typing import Optional
from collections.abc import Callable

from coreblocks.params.genparams import GenParams
from coreblocks.interface.keys import CSRListKey
from coreblocks.interface.layouts import CSRRegisterLayouts

from transactron import Method, def_method, TModule
from transactron.lib.transformers import MethodMap, MethodFilter
from transactron.utils.dependencies import DependencyContext
from transactron.utils.transactron_helpers import get_src_loc
from transactron.utils._typing import ValueLike, SrcLoc


class CSRRegister(Elaboratable):
    """CSR Register
    Used to define a CSR register and specify its behaviour.
    `CSRRegisters` are automatically assigned to `CSRListKey` dependency key, to be accessed from `CSRUnits`.

    Attributes
    ----------
    read: Method
        Reads register value and side effect status.
        Side effect fields `read` and `written` are set if register was accessed by `_fu_read` or `_fu_write`
        methods (by CSR instruction) in a current cycle; they can be used to trigger other actions.
        Always ready.
    read_comb: Method
        Reads register value or value submitted by `_fu_write`(instruction write) combinationally.
        Note that returned value ignores priority setting. It allows for `_fu_write -> read_comb -> write` operation
        in single cycle. Note that if `_fu_write` is called, it returns call value ignoring `ro_bits`. Always ready.
    write: Method
        Updates register value. Always ready.
    _fu_read: Method
        Method connected automatically by `CSRUnit`. Reads register value.
    _fu_write: Method
        Method connected automatically by `CSRUnit`. Updates register value. Always ready.

    Examples
    --------
    .. highlight:: python
    .. code-block:: python

        # Timer register that increments on each cycle and resets if read by CSR instruction
        csr = CSRRegister(1, gen_params)
        with Transaction.body(m):
            csr_val = csr.read()
            with m.If(csr_val.read):
                csr.write(0)
            with m.Else():
                csr.write(csr_val.data + 1)
    """

    def __init__(
        self,
        csr_number: Optional[int],
        gen_params: GenParams,
        *,
        width: Optional[int] = None,
        ro_bits: int = 0,
        init: int | Enum = 0,
        fu_write_priority: bool = True,
        fu_write_filtermap: Optional[Callable[[TModule, Value], tuple[ValueLike, ValueLike]]] = None,
        fu_read_map: Optional[Callable[[TModule, Value], ValueLike]] = None,
        src_loc: int | SrcLoc = 0,
    ):
        """
        Parameters
        ----------
        csr_number: Optional[int]
            Address of this CSR Register.
            If `None` is given, CSR is virtual - not automatically connected to CSRUnit.
        gen_params: GenParams
            Core generation parameters.
        width: Optional[int]
            Width of CSR register. Defaults to `xlen`.
        ro_bits: int
            Bit mask of read-only bits in register.
            Writes from `_fu_write` (instructions) to those bits are ignored.
            Note that this parameter is only required if there are some read-only
            bits in read-write register. Writes to read-only registers specified
            by upper 2 bits of CSR address set to `0b11` are discarded by `CSRUnit`.
        init: int | Enum
            Reset value of CSR.
        fu_write_priority: bool
            Priority of CSR instruction write over `write` method, if both are called at the same cycle.
            If `ro_bits` are set, both operations will be performed, respecting priority on writeable bits.
            Deafults to True.
        fu_write_filtermap: function (TModule, Value) -> (ValueLike, ValueLike)
            Filter + map on CSR writes from instruction. First Value in returned tuple signals if write should be
            performed, second is modified input data.
        fu_read_map: function (TModule, Value) -> (ValueLike)
            Map on CSR reads from instructions. Maps value returned from CSR.
        src_loc: int | SrcLoc
            How many stack frames deep the source location is taken from.
            Alternatively, the source location to use instead of the default.
        """
        self.gen_params = gen_params
        self.csr_number = csr_number
        self.width = width if width is not None else gen_params.isa.xlen
        self.ro_bits = ro_bits
        self.fu_write_priority = fu_write_priority
        fu_write_filtermap = fu_write_filtermap if fu_write_filtermap else (lambda _, ms: (C(1), ms))
        fu_read_map = fu_read_map if fu_read_map else (lambda _, ms: ms)
        self.src_loc = get_src_loc(src_loc)

        csr_layouts = gen_params.get(CSRRegisterLayouts, data_width=self.width)

        self.read = Method(o=csr_layouts.read)
        self.read_comb = Method(o=csr_layouts.read)
        self.write = Method(i=csr_layouts.write)

        self._internal_fu_read = Method(o=csr_layouts._fu_read)
        self._internal_fu_write = Method(i=csr_layouts._fu_write)
        self.fu_write_map = MethodMap(
            self._internal_fu_write,
            i_transform=(csr_layouts._fu_write, lambda tm, ms: {"data": fu_write_filtermap(tm, ms["data"])[1]}),
        )
        self.fu_write_filter = MethodFilter(
            self.fu_write_map.method, lambda tm, ms: fu_write_filtermap(tm, ms["data"])[0]
        )
        self.fu_read_map = MethodMap(
            self._internal_fu_read,
            o_transform=(csr_layouts._fu_read, lambda tm, ms: {"data": fu_read_map(tm, ms["data"])}),
        )

        # Methods connected automatically by CSRUnit
        self._fu_read = self.fu_read_map.method
        self._fu_write = self.fu_write_filter.method

        self.value = Signal(self.width, init=init)
        self.side_effects = Signal(StructLayout({"read": 1, "write": 1}))

        # append to global CSR list
        if csr_number is not None:
            dm = DependencyContext.get()
            dm.add_dependency(CSRListKey(), self)

        if csr_number and self.width != gen_params.isa.xlen:
            raise RuntimeError(f"Width of public CSR register is different than {gen_params.isa.xlen}")

    def elaborate(self, platform):
        m = TModule()

        internal_method_layout = StructLayout({"data": self.gen_params.isa.xlen, "active": 1})
        write_internal = Signal(internal_method_layout)
        fu_write_internal = Signal(internal_method_layout)

        m.d.sync += self.side_effects.eq(0)

        @def_method(m, self.write)
        def _(data):
            m.d.comb += write_internal.data.eq(data)
            m.d.comb += write_internal.active.eq(1)

        @def_method(m, self._internal_fu_write)
        def _(data):
            m.d.comb += fu_write_internal.data.eq(data)
            m.d.comb += fu_write_internal.active.eq(1)
            m.d.sync += self.side_effects.write.eq(1)

        @def_method(m, self.read, nonexclusive=True)
        def _():
            return {"data": self.value, "read": self.side_effects.read, "written": self.side_effects.write}

        @def_method(m, self._internal_fu_read)
        def _():
            m.d.sync += self.side_effects.read.eq(1)
            return self.value

        @def_method(m, self.read_comb, nonexclusive=True)
        def _():
            return {
                "data": Mux(self._internal_fu_write.run, fu_write_internal.data, self.value),
                "read": self._internal_fu_read.run,
                "written": self._internal_fu_write.run,
            }

        with m.If(fu_write_internal.active & write_internal.active):
            if self.fu_write_priority:
                m.d.sync += self.value.eq(
                    (fu_write_internal.data & ~self.ro_bits) | (write_internal.data & self.ro_bits)
                )
            else:
                m.d.sync += self.value.eq(write_internal.data)
        with m.Elif(fu_write_internal.active):
            m.d.sync += self.value.eq((fu_write_internal.data & ~self.ro_bits) | (self.value & self.ro_bits))
        with m.Elif(write_internal.active):
            m.d.sync += self.value.eq(write_internal.data)

        m.submodules.fu_write_filter = self.fu_write_filter
        m.submodules.fu_read_map = self.fu_read_map
        m.submodules.fu_write_map = self.fu_write_map

        return m
