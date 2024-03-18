from amaranth import *

from enum import IntFlag, auto, unique
from typing import Sequence


from transactron import *
from transactron.lib import BasicFifo
from transactron.utils import DependencyManager

from coreblocks.params import *
from coreblocks.params import GenParams, FunctionalComponentParams
from coreblocks.frontend.decoder import Funct3, OpType, Funct7, ExceptionCause
from coreblocks.interface.layouts import FuncUnitLayouts, RetirementLayouts, FetchLayouts
from coreblocks.interface.keys import MretKey, AsyncInterruptInsertSignalKey, ExceptionReportKey, GenericCSRRegistersKey, InstructionPrecommitKey, FetchResumeKey
from coreblocks.func_blocks.interface.func_protocols import FuncUnit

from coreblocks.func_blocks.fu.common.fu_decoder import DecoderManager


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

        self.fetch_resume_fifo = BasicFifo(self.gp.get(FetchLayouts).resume, 2)

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

        m.submodules.fetch_resume_fifo = self.fetch_resume_fifo

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
                # SPEC: "These conditions for an interrupt trap to occur [..] must also be evaluated immediately
                # following the execution of an xRET instruction."
                # mret() method is called from precommit() that was executed at least one cycle earlier (because
                # of finished condition). If calling mret() caused interrupt to be active, it is already represented
                # by updated async_interrupt_active singal.
                # Interrupt is reported on this xRET instruction with return address set to instruction that we
                # would normally return to (mepc value is preserved)
                m.d.comb += exception.eq(1)
                exception_report(m, cause=ExceptionCause._COREBLOCKS_ASYNC_INTERRUPT, pc=ret_pc, rob_id=instr_rob)
            with m.Else():
                # Unstall the fetch to return address (MRET is SYSTEM opcode)
                self.fetch_resume_fifo.write(m, pc=ret_pc, resume_from_exception=0)

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
        connections.add_dependency(FetchResumeKey(), unit.fetch_resume_fifo.read)
        return unit

    def get_optypes(self) -> set[OpType]:
        return PrivilegedFn().get_op_types()
