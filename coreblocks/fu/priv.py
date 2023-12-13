from amaranth import *

from enum import IntFlag, auto
from typing import Sequence


from transactron import *
from transactron.utils.fifo import BasicFifo

from coreblocks.params import *
from coreblocks.params.keys import MretKey
from coreblocks.utils.protocols import FuncUnit

from coreblocks.fu.fu_decoder import DecoderManager


class PrivilegedFn(DecoderManager):
    @unique
    class Fn(IntFlag):
        MRET = auto()

    @classmethod
    def get_instructions(cls) -> Sequence[tuple]:
        return [(cls.Fn.MRET, OpType.MRET)]


class PrivilegedFuncUnit(Elaboratable):
    def __init__(self, gp: GenParams):
        self.gp = gp

        self.layouts = layouts = gp.get(FuncUnitLayouts)
        self.dm = gp.get(DependencyManager)

        self.issue = Method(i=layouts.issue)
        self.accept = Method(o=layouts.accept)
        self.precommit = Method(i=gp.get(RetirementLayouts).precommit)

        self.branch_resolved_fifo = BasicFifo(self.gp.get(FetchLayouts).branch_verify, 2)

    def elaborate(self, platform):
        m = TModule()

        instr_valid = Signal()
        finished = Signal()

        instr_rob = Signal(self.gp.rob_entries_bits)
        instr_pc = Signal(self.gp.isa.xlen)

        mret = self.dm.get_dependency(MretKey())
        async_interrupt_active = self.dm.get_dependency(AsyncInterruptInsertSignalKey())
        exception_report = self.dm.get_dependency(ExceptionReportKey())
        csr = self.dm.get_dependency(GenericCSRRegistersKey())

        m.submodules.branch_resolved_fifo = self.branch_resolved_fifo

        @def_method(m, self.issue, ready=~instr_valid)
        def _(arg):
            m.d.sync += [
                instr_valid.eq(1),
                instr_rob.eq(arg.rob_id),
                instr_pc.eq(arg.pc),
            ]

        @def_method(m, self.precommit)
        def _(rob_id, side_fx):
            with m.If(instr_valid & (rob_id == instr_rob)):
                m.d.sync += finished.eq(1)
                with m.If(side_fx):
                    mret(m)

        @def_method(m, self.accept, ready=instr_valid & finished)
        def _():
            m.d.sync += instr_valid.eq(0)
            m.d.sync += finished.eq(0)

            ret_pc = csr.m_mode.mepc.read(m).data

            exception = Signal()
            with m.If(async_interrupt_active):
                # If mret caused activating interrupt, it is needed to evaulate it immediately (from SPEC).
                # This method has at least one cycle delay from precommit, so new interrupt signal is already computed.
                # Report new interrupt with the same mepc
                m.d.comb += exception.eq(1)
                exception_report(m, cause=ExceptionCause._COREBLOCKS_ASYNC_INTERRUPT, pc=ret_pc, rob_id=instr_rob)
            with m.Else():
                # Unstall the fetch to return address (MRET is SYSTEM opcode)
                self.branch_resolved_fifo.write(m, next_pc=ret_pc, from_pc=0, resume_from_exception=0)

            return {
                "rob_id": instr_rob,
                "exception": exception,
                "rp_dst": 0,
                "result": 0,
            }

        return m


class PrivilegedUnitComponent(FunctionalComponentParams):
    def get_module(self, gp: GenParams) -> FuncUnit:
        unit = PrivilegedFuncUnit(gp)
        connections = gp.get(DependencyManager)
        connections.add_dependency(InstructionPrecommitKey(), unit.precommit)
        connections.add_dependency(BranchResolvedKey(), unit.branch_resolved_fifo.read)
        return unit

    def get_optypes(self) -> set[OpType]:
        return PrivilegedFn().get_op_types()
