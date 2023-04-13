from amaranth import *

from coreblocks.transactions import Method, def_method, Transaction
from coreblocks.utils import assign
from coreblocks.params.genparams import GenParams
from coreblocks.params.layouts import FuncUnitLayouts, CSRLayouts
from coreblocks.params.isa import Funct3
from coreblocks.params.optypes import OpType


class CSRRegister(Elaboratable):
    """CSR Register
    Used to define a CSR register and specify its behaviour.
    `CSRRegister`s need to be registered to a `CSRUnit` in order to be
    accesible by instructions.

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
        csr = CSRRegister(1, gp)
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
        self.side_effects = Record({("read", 1), ("write", 1)})

    def elaborate(self, platform):
        m = Module()

        internal_method_layout = {("data", self.gen_params.isa.xlen), ("active", 1)}
        write_internal = Record(internal_method_layout)
        fu_write_internal = Record(internal_method_layout)

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


class CSRUnit(Elaboratable):
    """
    Unit for performing Control and Status Regitsters computations.

    Accepts instructions with `OpType.CSR_REG` and `OpType.CSR_IMM`.
    Uses `RS` interface for input and `FU` interface for output.
    Depends on stalling the `Fetch` stage on CSR instructions and holds computation
    unitl all other instructions are commited.

    Each CSR register have to be specified by `CSRRegister` class and
    registered by `register` method.

    Attributes
    ----------
    select: Method
        Method from standard RS interface. Reserves a place for instruction.
    insert: Method
        Method from standard RS interface. Puts instruction in reserved place.
    update: Method
        Method from standard RS interface. Receives announcements of computed register values.
    accept: Method
        Method from standard FU interface. Used to receive instruction result and pass it
        to the next pipeline stage.
    """

    def __init__(self, gen_params: GenParams, rob_single_instr: Signal, fetch_continue: Method):
        """
        Parameters
        ----------
        gen_params: GenParams
            Core generation parameters.
        rob_single_instr: Signal, in
            Signalls that there is only one instruction left in `ROB`.
        fetch_continue: Method
            Method to resume `Fetch` unit from stalled PC.
        """
        self.gen_params = gen_params

        self.rob_empty = rob_single_instr
        self.fetch_continue = fetch_continue

        # Standard RS interface
        self.csr_layouts = gen_params.get(CSRLayouts)
        self.fu_layouts = gen_params.get(FuncUnitLayouts)
        self.select = Method(o=self.csr_layouts.rs_select_out)
        self.insert = Method(i=self.csr_layouts.rs_insert_in)
        self.update = Method(i=self.csr_layouts.rs_update_in)
        self.accept = Method(o=self.fu_layouts.accept)

        self.regfile: dict[int, tuple[Method, Method]] = {}

    def register(self, csr: CSRRegister):
        """
        Registers `CSRRegister` - makes it accesible by this unit.
        Call this method from other constructors.

        Parameters
        ----------
        csr: CSRRegister
            `CSRRegister` to register.
        """
        if csr.csr_number in self.regfile:
            raise RuntimeError(f"CSR number {csr.csr_number} already registered")
        self.regfile[csr.csr_number] = (csr._fu_read, csr._fu_write)

    def elaborate(self, platform):
        m = Module()

        reserved = Signal()
        ready_to_process = Signal()
        done = Signal()

        current_result = Signal(self.gen_params.isa.xlen)

        instr = Record(self.csr_layouts.rs_data_layout + [("valid", 1)])

        m.d.comb += ready_to_process.eq(self.rob_empty & instr.valid & (instr.rp_s1 == 0))

        # RISCV Zicsr spec Table 1.1
        should_read_csr = Signal()
        m.d.comb += should_read_csr.eq(
            ((instr.exec_fn.funct3 == Funct3.CSRRW) & (instr.rp_dst != 0))
            | (instr.exec_fn.funct3 == Funct3.CSRRS)
            | (instr.exec_fn.funct3 == Funct3.CSRRC)
            | ((instr.exec_fn.funct3 == Funct3.CSRRWI) & (instr.rp_dst != 0))
            | (instr.exec_fn.funct3 == Funct3.CSRRSI)
            | (instr.exec_fn.funct3 == Funct3.CSRRCI)
        )

        should_write_csr = Signal()
        m.d.comb += should_write_csr.eq(
            (instr.exec_fn.funct3 == Funct3.CSRRW)
            | ((instr.exec_fn.funct3 == Funct3.CSRRS) & (instr.rp_s1_reg != 0))  # original register number
            | ((instr.exec_fn.funct3 == Funct3.CSRRC) & (instr.rp_s1_reg != 0))
            | (instr.exec_fn.funct3 == Funct3.CSRRWI)
            | ((instr.exec_fn.funct3 == Funct3.CSRRSI) & (instr.s1_val != 0))
            | ((instr.exec_fn.funct3 == Funct3.CSRRCI) & (instr.s1_val != 0))
        )

        # Methods used within this Tranaction are CSRRegister internal _fu_(read|write) handlers which are always ready
        with Transaction().body(m, request=(ready_to_process & ~done)):
            with m.Switch(instr.csr):
                for csr_number, methods in self.regfile.items():
                    read, write = methods
                    with m.Case(csr_number):
                        read_val = Signal(self.gen_params.isa.xlen)
                        with m.If(should_read_csr & ~done):
                            m.d.comb += read_val.eq(read(m))
                            m.d.sync += current_result.eq(read_val)

                        with m.If(should_write_csr & ~done):
                            write_val = Signal(self.gen_params.isa.xlen)
                            with m.If((instr.exec_fn.funct3 == Funct3.CSRRW) | (instr.exec_fn.funct3 == Funct3.CSRRWI)):
                                m.d.comb += write_val.eq(instr.s1_val)
                            with m.If((instr.exec_fn.funct3 == Funct3.CSRRS) | (instr.exec_fn.funct3 == Funct3.CSRRSI)):
                                m.d.comb += write_val.eq(read_val | instr.s1_val)
                            with m.If((instr.exec_fn.funct3 == Funct3.CSRRC) | (instr.exec_fn.funct3 == Funct3.CSRRCI)):
                                m.d.comb += write_val.eq(read_val & (~instr.s1_val))

                            write(m, write_val)
                with m.Default():
                    pass  # TODO : invalid csr number handling

            m.d.sync += done.eq(1)

        @def_method(m, self.select, ~reserved)
        def _():
            m.d.sync += reserved.eq(1)
            return {"rs_entry_id": 0}  # only one CSR instruction is allowed

        @def_method(m, self.insert)
        def _(rs_entry_id, rs_data):
            m.d.sync += assign(instr, rs_data)

            with m.If(rs_data.exec_fn.op_type == OpType.CSR_IMM):  # Pass immediate as first operand
                m.d.sync += instr.s1_val.eq(rs_data.imm)

            m.d.sync += instr.valid.eq(1)

        @def_method(m, self.update)
        def _(tag, value):
            with m.If(tag == instr.rp_s1):
                m.d.sync += instr.s1_val.eq(value)
                m.d.sync += instr.rp_s1.eq(0)

        @def_method(m, self.accept, done)
        def _():
            m.d.sync += reserved.eq(0)
            m.d.sync += instr.valid.eq(0)
            m.d.sync += done.eq(0)
            self.fetch_continue(m)
            return {
                "rob_id": instr.rob_id,
                "rp_dst": instr.rp_dst,
                "result": current_result,
            }

        return m
