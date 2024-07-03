from amaranth import *
from amaranth.lib.data import StructLayout
from dataclasses import dataclass

from transactron import Method, def_method, Transaction, TModule
from transactron.utils import assign
from transactron.utils.data_repr import bits_from_int
from transactron.utils.dependencies import DependencyContext

from coreblocks.arch import OpType, Funct3, ExceptionCause, PrivilegeLevel
from coreblocks.params import GenParams
from coreblocks.params.fu_params import BlockComponentParams
from coreblocks.func_blocks.interface.func_protocols import FuncBlock
from coreblocks.interface.layouts import FuncUnitLayouts, CSRUnitLayouts
from coreblocks.interface.keys import (
    CSRListKey,
    FetchResumeKey,
    InstructionPrecommitKey,
    ExceptionReportKey,
    AsyncInterruptInsertSignalKey,
)


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


class CSRUnit(FuncBlock, Elaboratable):
    """
    Unit for performing Control and Status Regitsters computations.

    Accepts instructions with `OpType.CSR_REG` and `OpType.CSR_IMM`.
    Uses `RS` interface for input and `FU` interface for output.
    Depends on stalling the `Fetch` stage on CSR instructions and holds computation
    unitl all other instructions are commited.

    Each CSR register have to be specified by `CSRRegister` class.

    Attributes
    ----------
    select: Method
        Method from standard RS interface. Reserves a place for instruction.
    insert: Method
        Method from standard RS interface. Puts instruction in reserved place.
    update: Method
        Method from standard RS interface. Receives announcements of computed register values.
    get_result: Method
        `accept` method from standard FU interface. Used to receive instruction result and pass it
        to the next pipeline stage.
    """

    def __init__(self, gen_params: GenParams):
        """
        Parameters
        ----------
        gen_params: GenParams
            Core generation parameters.
        """
        self.gen_params = gen_params
        self.dependency_manager = DependencyContext.get()

        # Standard RS interface
        self.csr_layouts = gen_params.get(CSRUnitLayouts)
        self.fu_layouts = gen_params.get(FuncUnitLayouts)
        self.select = Method(o=self.csr_layouts.rs.select_out)
        self.insert = Method(i=self.csr_layouts.rs.insert_in)
        self.update = Method(i=self.csr_layouts.rs.update_in)
        self.get_result = Method(o=self.fu_layouts.accept)

        self.regfile: dict[int, tuple[Method, Method]] = {}

    def _create_regfile(self):
        # Fills `self.regfile` with `CSRRegister`s provided by `CSRListKey` dependency.
        for csr in self.dependency_manager.get_dependency(CSRListKey()):
            assert csr.csr_number is not None
            if csr.csr_number in self.regfile:
                raise RuntimeError(f"CSR number {csr.csr_number} already registered")
            self.regfile[csr.csr_number] = (csr._fu_read, csr._fu_write)

    def elaborate(self, platform):
        self._create_regfile()

        m = TModule()

        reserved = Signal()
        ready_to_process = Signal()
        done = Signal()
        exception = Signal()
        precommitting = Signal()

        current_result = Signal(self.gen_params.isa.xlen)

        instr = Signal(StructLayout(self.csr_layouts.rs.data_layout.members | {"valid": 1}))

        m.d.comb += ready_to_process.eq(precommitting & instr.valid & (instr.rp_s1 == 0))

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

        # Temporary, until privileged spec is implemented
        priv_level = Signal(PrivilegeLevel, reset=PrivilegeLevel.MACHINE)

        exe_side_fx = Signal()

        # Methods used within this Tranaction are CSRRegister internal _fu_(read|write) handlers which are always ready
        with Transaction().body(m, request=(ready_to_process & ~done)):
            with m.Switch(instr.csr):
                for csr_number, methods in self.regfile.items():
                    read, write = methods
                    priv_level_required, read_only = csr_access_privilege(csr_number)

                    with m.Case(csr_number):
                        priv_valid = Signal()
                        m.d.comb += priv_valid.eq(priv_level_required <= priv_level)

                        with m.If(priv_valid):
                            read_val = Signal(self.gen_params.isa.xlen)
                            with m.If(should_read_csr & ~done):
                                with m.If(exe_side_fx):
                                    m.d.comb += read_val.eq(read(m))
                                m.d.sync += current_result.eq(read_val)

                            if read_only:
                                with m.If(should_write_csr):
                                    # Write to read only
                                    m.d.sync += exception.eq(1)
                            else:
                                with m.If(should_write_csr & ~done):
                                    write_val = Signal(self.gen_params.isa.xlen)
                                    with m.Switch(instr.exec_fn.funct3):
                                        with m.Case(Funct3.CSRRW, Funct3.CSRRWI):
                                            m.d.comb += write_val.eq(instr.s1_val)
                                        with m.Case(Funct3.CSRRS, Funct3.CSRRSI):
                                            m.d.comb += write_val.eq(read_val | instr.s1_val)
                                        with m.Case(Funct3.CSRRC, Funct3.CSRRCI):
                                            m.d.comb += write_val.eq(read_val & (~instr.s1_val))
                                    with m.If(exe_side_fx):
                                        write(m, write_val)

                        with m.Else():
                            # Missing privilege
                            m.d.sync += exception.eq(1)

                with m.Default():
                    # Invalid CSR number
                    m.d.sync += exception.eq(1)

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
        def _(reg_id, reg_val):
            with m.If(reg_id == instr.rp_s1):
                m.d.sync += instr.s1_val.eq(reg_val)
                m.d.sync += instr.rp_s1.eq(0)

        @def_method(m, self.get_result, done)
        def _():
            m.d.sync += reserved.eq(0)
            m.d.sync += instr.valid.eq(0)
            m.d.sync += done.eq(0)

            report = self.dependency_manager.get_dependency(ExceptionReportKey())
            interrupt = self.dependency_manager.get_dependency(AsyncInterruptInsertSignalKey())
            fetch_resume = self.dependency_manager.get_dependency(FetchResumeKey())

            with m.If(exception):
                report(m, rob_id=instr.rob_id, cause=ExceptionCause.ILLEGAL_INSTRUCTION, pc=instr.pc)
            with m.Elif(interrupt):
                # SPEC: "These conditions for an interrupt trap to occur [..] must also be evaluated immediately
                # following  [..] an explicit write to a CSR on which these interrupt trap conditions expressly depend."
                # At this time CSR operation is finished. If it caused triggering an interrupt, it would be represented
                # by interrupt signal in this cycle.
                # CSR instructions are never compressed, PC+4 is always next instruction
                report(
                    m,
                    rob_id=instr.rob_id,
                    cause=ExceptionCause._COREBLOCKS_ASYNC_INTERRUPT,
                    pc=instr.pc + self.gen_params.isa.ilen_bytes,
                )

            m.d.sync += exception.eq(0)

            with m.If(exe_side_fx & ~exception & ~interrupt):
                fetch_resume(m, pc=instr.pc + self.gen_params.isa.ilen_bytes, from_exception=0)

            return {
                "rob_id": instr.rob_id,
                "rp_dst": instr.rp_dst,
                "result": current_result,
                "exception": exception | interrupt,
            }

        # Generate precommitting signal from precommit
        with Transaction().body(m):
            precommit = self.dependency_manager.get_dependency(InstructionPrecommitKey())
            info = precommit(m)
            with m.If(instr.rob_id == info.rob_id):
                m.d.comb += precommitting.eq(1)
                m.d.comb += exe_side_fx.eq(info.side_fx)

        return m


@dataclass(frozen=True)
class CSRBlockComponent(BlockComponentParams):
    def get_module(self, gen_params: GenParams) -> FuncBlock:
        return CSRUnit(gen_params)

    def get_optypes(self) -> set[OpType]:
        return {OpType.CSR_REG, OpType.CSR_IMM}

    def get_rs_entry_count(self) -> int:
        return 1
