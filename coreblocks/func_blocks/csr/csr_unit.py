from amaranth import *
from amaranth.lib.data import StructLayout, View

from dataclasses import dataclass

from transactron import Method, Methods, def_method, def_methods, Transaction, TModule
from transactron.utils import assign
from transactron.utils.data_repr import bits_from_int
from transactron.utils.dependencies import DependencyContext
from transactron.lib.simultaneous import condition

from coreblocks.arch import OpType, Funct3, ExceptionCause, PrivilegeLevel
from coreblocks.arch.isa_consts import Opcode
from coreblocks.params import GenParams
from coreblocks.params.fu_params import BlockComponentParams
from coreblocks.func_blocks.csr.csr_protocol import RegisteredCSRProtocol
from coreblocks.func_blocks.interface.func_protocols import FuncBlock
from coreblocks.interface.layouts import FuncUnitLayouts, CSRUnitLayouts, RSInterfaceLayouts
from coreblocks.interface.keys import (
    CSRListKey,
    UnsafeInstructionResolvedKey,
    CSRInstancesKey,
    InstructionPrecommitKey,
    ExceptionReportKey,
    AsyncInterruptInsertSignalKey,
)

__all__ = [
    "CSRUnit",
    "CSRBlockComponent",
]


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
        Method from standard RS func block interface. Used to receive instruction result and pass
        it to the next pipeline stage.
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
        self.update = Methods(gen_params.announcement_superscalarity, i=self.csr_layouts.rs.update_in)
        self.get_result = Method(o=self.fu_layouts.push_result)

        self.regfile: dict[int, RegisteredCSRProtocol] = {}

        self.report = self.dependency_manager.get_dependency(ExceptionReportKey())()

    def _create_regfile(self):
        # Fills `self.regfile` with CSR registers provided by `CSRListKey` dependency.
        for csr_number, csr in self.dependency_manager.get_dependency(CSRListKey()):
            if csr_number in self.regfile:
                raise RuntimeError(
                    f"CSR number 0x{csr_number:03x} already registered at {self.regfile[csr_number].src_loc}"
                    f" and {csr.src_loc}"
                )
            self.regfile[csr_number] = csr

    @staticmethod
    def _csr_access_privilege(csr_addr: int) -> tuple[PrivilegeLevel, bool]:
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

    def elaborate(self, platform):
        self._create_regfile()

        m = TModule()

        reserved = Signal()
        ready_to_process = Signal()
        done = Signal()
        exception = Signal()

        current_result = Signal(self.gen_params.isa.xlen)

        instr = Signal(StructLayout(self.csr_layouts.rs.data_layout.members | {"valid": 1}))

        m.d.comb += ready_to_process.eq(instr.valid & (instr.rp_s1 == 0))

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

        exe_side_fx = Signal()

        # Methods used within this Tranaction are CSRRegister internal _fu_(read|write) handlers which are always ready
        with Transaction().body(m, ready=(ready_to_process & ~done)):
            precommit = self.dependency_manager.get_dependency(InstructionPrecommitKey())
            info = precommit(m, instr.rob_id)
            m.d.top_comb += exe_side_fx.eq(info.side_fx)
            csr_instances = self.dependency_manager.get_dependency(CSRInstancesKey())
            current_priv_mode = csr_instances.m_mode.priv_mode.read(m).data

            # Use condition() as a workaround for kuznia-rdzeni/transactron#10, as _fu_(read|write) methods
            # are called multiple times, as some CSRs are aliased call other CSR's _fu_* methods.
            with condition(m) as branch:
                for csr_number, csr in self.regfile.items():
                    priv_level_required, read_only = self._csr_access_privilege(csr_number)

                    with branch(instr.csr == csr_number):
                        priv_valid = Signal()
                        csr_access_valid = csr._fu_access_valid(m, current_priv_mode).valid

                        m.d.comb += priv_valid.eq(priv_level_required <= current_priv_mode)

                        with m.If(priv_valid & csr_access_valid):
                            read_val = Signal(self.gen_params.isa.xlen)
                            with m.If(should_read_csr & ~done):
                                with m.If(exe_side_fx):
                                    m.d.comb += read_val.eq(csr._fu_read(m))
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
                                        csr._fu_write(m, write_val)

                        with m.Else():
                            # Missing privilege
                            m.d.sync += exception.eq(1)

                with branch():
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
                m.d.sync += instr.s1_val.eq(rs_data.imm[0:5])

            m.d.sync += instr.valid.eq(1)

        @def_methods(m, self.update)
        def _(k: int, reg_id, reg_val):
            with m.If(reg_id == instr.rp_s1):
                m.d.sync += instr.s1_val.eq(reg_val)
                m.d.sync += instr.rp_s1.eq(0)

        @def_method(m, self.get_result, done)
        def _():
            m.d.sync += reserved.eq(0)
            m.d.sync += instr.valid.eq(0)
            m.d.sync += done.eq(0)

            interrupt = self.dependency_manager.get_dependency(AsyncInterruptInsertSignalKey())
            resume_core = self.dependency_manager.get_dependency(UnsafeInstructionResolvedKey())

            with m.If(exception):
                mtval = Signal(self.gen_params.isa.xlen)
                # re-encode the CSR instruction to speed-up missing CSR emulation (optional, otherwise mtval must be 0)
                imm_view = View(self.csr_layouts.imm_layout, instr.imm)

                m.d.av_comb += mtval[0:2].eq(0b11)
                m.d.av_comb += mtval[2:7].eq(Opcode.SYSTEM)
                m.d.av_comb += mtval[7:12].eq(imm_view.rd)
                m.d.av_comb += mtval[12:15].eq(instr.exec_fn.funct3)
                m.d.av_comb += mtval[15:20].eq(
                    Mux(
                        instr.exec_fn.op_type == OpType.CSR_IMM,
                        imm_view.imm,
                        imm_view.rs1,
                    )
                )
                m.d.av_comb += mtval[20:32].eq(instr.csr)
                self.report(m, rob_id=instr.rob_id, cause=ExceptionCause.ILLEGAL_INSTRUCTION, pc=instr.pc, mtval=mtval)
            with m.Elif(interrupt):
                # SPEC: "These conditions for an interrupt trap to occur [..] must also be evaluated immediately
                # following  [..] an explicit write to a CSR on which these interrupt trap conditions expressly depend."
                # At this time CSR operation is finished. If it caused triggering an interrupt, it would be represented
                # by interrupt signal in this cycle.
                # CSR instructions are never compressed, PC+4 is always next instruction
                self.report(
                    m,
                    rob_id=instr.rob_id,
                    cause=ExceptionCause._COREBLOCKS_ASYNC_INTERRUPT,
                    pc=instr.pc + self.gen_params.isa.ilen_bytes,
                    mtval=0,
                )

            m.d.sync += exception.eq(0)

            with m.If(exe_side_fx & ~exception & ~interrupt):
                # CSR instructions are never compressed, PC+4 is always next instruction
                resume_core(m, pc=instr.pc + self.gen_params.isa.ilen_bytes)

            return {
                "rob_id": instr.rob_id,
                "rp_dst": instr.rp_dst,
                "result": current_result,
                "exception": exception | interrupt,
            }

        return m


@dataclass(frozen=True)
class CSRBlockComponent(BlockComponentParams):
    def get_module(self, gen_params: GenParams) -> FuncBlock:
        return CSRUnit(gen_params)

    def get_optypes(self) -> set[OpType]:
        return {OpType.CSR_REG, OpType.CSR_IMM}

    def get_layouts(self, gen_params: GenParams) -> RSInterfaceLayouts:
        return gen_params.get(CSRUnitLayouts).rs

    def get_rs_entry_count(self) -> int:
        return 1
