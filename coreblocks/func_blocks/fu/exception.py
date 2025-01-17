from dataclasses import dataclass
from typing import Sequence
from amaranth import *
from coreblocks.arch.isa_consts import PrivilegeLevel
from transactron.utils.dependencies import DependencyContext

from transactron import *
from transactron.lib import FIFO

from coreblocks.params import GenParams, FunctionalComponentParams
from coreblocks.arch import OpType, Funct3, ExceptionCause
from coreblocks.interface.layouts import FetchLayouts, FuncUnitLayouts
from transactron.utils import OneHotSwitch
from coreblocks.interface.keys import ExceptionReportKey, CSRInstancesKey

from coreblocks.func_blocks.fu.common.fu_decoder import DecoderManager
from enum import IntFlag, auto

from coreblocks.func_blocks.interface.func_protocols import FuncUnit

__all__ = ["ExceptionFuncUnit", "ExceptionUnitComponent"]


class ExceptionUnitFn(DecoderManager):
    class Fn(IntFlag):
        ECALL = auto()
        EBREAK = auto()
        # Fns representing exceptions caused by instructions before FUs
        INSTR_ACCESS_FAULT = auto()
        ILLEGAL_INSTRUCTION = auto()
        BREAKPOINT = auto()
        INSTR_PAGE_FAULT = auto()

    def get_instructions(self) -> Sequence[tuple]:
        return [
            (self.Fn.ECALL, OpType.ECALL),
            (self.Fn.EBREAK, OpType.EBREAK),
            (self.Fn.INSTR_ACCESS_FAULT, OpType.EXCEPTION, Funct3._EINSTRACCESSFAULT),
            (self.Fn.ILLEGAL_INSTRUCTION, OpType.EXCEPTION, Funct3._EILLEGALINSTR),
            (self.Fn.BREAKPOINT, OpType.EXCEPTION, Funct3._EBREAKPOINT),
            (self.Fn.INSTR_PAGE_FAULT, OpType.EXCEPTION, Funct3._EINSTRPAGEFAULT),
        ]


class ExceptionFuncUnit(FuncUnit, Elaboratable):
    def __init__(self, gen_params: GenParams, unit_fn=ExceptionUnitFn()):
        self.gen_params = gen_params
        self.fn = unit_fn

        layouts = gen_params.get(FuncUnitLayouts)

        self.issue = Method(i=layouts.issue)
        self.accept = Method(o=layouts.accept)

        self.dm = DependencyContext.get()
        self.report = self.dm.get_dependency(ExceptionReportKey())

    def elaborate(self, platform):
        m = TModule()

        m.submodules.fifo = fifo = FIFO(self.gen_params.get(FuncUnitLayouts).accept, 2)
        m.submodules.decoder = decoder = self.fn.get_decoder(self.gen_params)

        @def_method(m, self.accept)
        def _():
            return fifo.read(m)

        @def_method(m, self.issue)
        def _(arg):
            m.d.comb += decoder.exec_fn.eq(arg.exec_fn)

            cause = Signal(ExceptionCause)
            mtval = Signal(self.gen_params.isa.xlen)

            priv_level = self.dm.get_dependency(CSRInstancesKey()).m_mode.priv_mode.read(m).data

            with OneHotSwitch(m, decoder.decode_fn) as OneHotCase:
                with OneHotCase(ExceptionUnitFn.Fn.EBREAK):
                    m.d.av_comb += cause.eq(ExceptionCause.BREAKPOINT)
                    m.d.av_comb += mtval.eq(arg.pc)
                with OneHotCase(ExceptionUnitFn.Fn.ECALL):
                    with m.Switch(priv_level):
                        with m.Case(PrivilegeLevel.MACHINE):
                            m.d.av_comb += cause.eq(ExceptionCause.ENVIRONMENT_CALL_FROM_M)
                        with m.Case(PrivilegeLevel.USER):
                            m.d.av_comb += cause.eq(ExceptionCause.ENVIRONMENT_CALL_FROM_U)
                    m.d.av_comb += mtval.eq(0)  # by SPEC
                with OneHotCase(ExceptionUnitFn.Fn.INSTR_ACCESS_FAULT):
                    m.d.av_comb += cause.eq(ExceptionCause.INSTRUCTION_ACCESS_FAULT)
                    # With C extension access fault can be only on the second half of instruction, and mepc != mtval.
                    # This information is passed in imm field
                    m.d.av_comb += mtval.eq(
                        arg.pc + ((arg.imm & FetchLayouts.AccessFaultFlag.ACCESS_FAULT_ON_SECOND_HALF).any() << 1)
                    )
                with OneHotCase(ExceptionUnitFn.Fn.ILLEGAL_INSTRUCTION):
                    m.d.av_comb += cause.eq(ExceptionCause.ILLEGAL_INSTRUCTION)
                    m.d.av_comb += mtval.eq(arg.imm)  # passed instruction bytes
                with OneHotCase(ExceptionUnitFn.Fn.BREAKPOINT):
                    m.d.av_comb += cause.eq(ExceptionCause.BREAKPOINT)
                    m.d.av_comb += mtval.eq(arg.pc)
                with OneHotCase(ExceptionUnitFn.Fn.INSTR_PAGE_FAULT):
                    m.d.av_comb += cause.eq(ExceptionCause.INSTRUCTION_PAGE_FAULT)
                    m.d.av_comb += mtval.eq(arg.pc + (arg.imm[1] << 1))

            self.report(m, rob_id=arg.rob_id, cause=cause, pc=arg.pc, mtval=mtval)

            fifo.write(m, result=0, exception=1, rob_id=arg.rob_id, rp_dst=arg.rp_dst)

        return m


@dataclass(frozen=True)
class ExceptionUnitComponent(FunctionalComponentParams):
    decoder_manager: ExceptionUnitFn = ExceptionUnitFn()

    def get_module(self, gen_params: GenParams) -> FuncUnit:
        return ExceptionFuncUnit(gen_params, self.decoder_manager)
