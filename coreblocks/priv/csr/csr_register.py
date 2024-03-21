from amaranth import *
from amaranth.lib.data import StructLayout
from amaranth.lib.enum import IntEnum
from dataclasses import dataclass

from transactron import Method, def_method, TModule
from transactron.utils import bits_from_int
from coreblocks.params.genparams import GenParams
from transactron.utils.dependencies import DependencyManager, ListKey
from coreblocks.interface.layouts import CSRLayouts
from transactron.utils.transactron_helpers import from_method_layout


class PrivilegeLevel(IntEnum, shape=2):
    USER = 0b00
    SUPERVISOR = 0b01
    MACHINE = 0b11


def csr_access_privilege(csr_addr: int) -> tuple[PrivilegeLevel, bool]:
    read_only = bits_from_int(csr_addr, 10, 2) == 0b11

    match bits_from_int(csr_addr, 8, 2):
        case 0b00:
            return (PrivilegeLevel.USER, read_only)
        case 0b01:
            return (PrivilegeLevel.SUPERVISOR, read_only)
        case 0b10:  # Hypervisior CSRs - accessible with VS mode (S with extension)
            return (PrivilegeLevel.SUPERVISOR, read_only)
        case _:
            return (PrivilegeLevel.MACHINE, read_only)


@dataclass(frozen=True)
class CSRListKey(ListKey["CSRRegister"]):
    """DependencyManager key collecting CSR registers globally as a list."""

    # This key is defined here, because it is only used internally by CSRRegister and CSRUnit
    pass


class CSRRegister(Elaboratable):
    """CSR Register
    Used to define a CSR register and specify its behaviour.
    `CSRRegisters` are automatically assigned to `CSRListKey` dependency key, to be accessed from `CSRUnits`.

    Attributes
    ----------
    read: Method
        Reads register value and side effect status.
        Side effect fields `read` and `written` are set if register was accessed by _fu_read or _fu_write
        methods (by CSR instruction) in a current cycle; they can be used to trigger other actions.
        Always ready.
    write: Method
        Updates register value.
        Always ready. If _fu_write is called simultaneously, this call is ignored.
    _fu_read: Method
        Method connected automatically by `CSRUnit`. Reads register value.
    _fu_write: Method
        Method connected automatically by `CSRUnit`. Updates register value.
        Always ready. Has priority over `write` method.

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

    def __init__(self, csr_number: int, gen_params: GenParams, *, ro_bits: int = 0):
        """
        Parameters
        ----------
        csr_number: int
            Address of this CSR Register.
        gen_params: GenParams
            Core generation parameters.
        ro_bits: int
            Bit mask of read-only bits in register.
            Writes from _fu_write (instructions) to those bits are ignored.
            Note that this parameter is only required if there are some read-only
            bits in read-write register. Writes to read-only registers specified
            by upper 2 bits of CSR address set to `0b11` are discarded by `CSRUnit`.
        """
        self.gen_params = gen_params
        self.csr_number = csr_number
        self.ro_bits = ro_bits

        csr_layouts = gen_params.get(CSRLayouts)

        self.read = Method(o=csr_layouts.read)
        self.write = Method(i=csr_layouts.write)

        # Methods connected automatically by CSRUnit
        self._fu_read = Method(o=csr_layouts._fu_read)
        self._fu_write = Method(i=csr_layouts._fu_write)

        self.value = Signal(gen_params.isa.xlen)
        self.side_effects = Signal(StructLayout({"read": 1, "write": 1}))

        # append to global CSR list
        dm = gen_params.get(DependencyManager)
        dm.add_dependency(CSRListKey(), self)

    def elaborate(self, platform):
        m = TModule()

        internal_method_layout = from_method_layout([("data", self.gen_params.isa.xlen), ("active", 1)])
        write_internal = Signal(internal_method_layout)
        fu_write_internal = Signal(internal_method_layout)

        m.d.sync += self.side_effects.eq(0)

        @def_method(m, self.write)
        def _(data):
            m.d.comb += write_internal.data.eq(data)
            m.d.comb += write_internal.active.eq(1)

        @def_method(m, self._fu_write)
        def _(data):
            m.d.comb += fu_write_internal.data.eq(data)
            m.d.comb += fu_write_internal.active.eq(1)
            m.d.sync += self.side_effects.write.eq(1)

        @def_method(m, self.read)
        def _():
            return {"data": self.value, "read": self.side_effects.read, "written": self.side_effects.write}

        @def_method(m, self._fu_read)
        def _():
            m.d.sync += self.side_effects.read.eq(1)
            return self.value

        # Writes from instructions have priority
        with m.If(fu_write_internal.active & write_internal.active):
            m.d.sync += self.value.eq((fu_write_internal.data & ~self.ro_bits) | (write_internal.data & self.ro_bits))
        with m.Elif(fu_write_internal.active):
            m.d.sync += self.value.eq((fu_write_internal.data & ~self.ro_bits) | (self.value & self.ro_bits))
        with m.Elif(write_internal.active):
            m.d.sync += self.value.eq(write_internal.data)

        return m
