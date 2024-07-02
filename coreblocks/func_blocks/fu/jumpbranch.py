from amaranth import *

from enum import IntFlag, auto

from typing import Sequence

from transactron import *
from transactron.core import def_method
from transactron.lib import *
from transactron.lib import logging
from transactron.utils import DependencyContext
from coreblocks.params import GenParams, FunctionalComponentParams
from coreblocks.arch import Funct3, OpType, ExceptionCause, Extension
from coreblocks.interface.layouts import FuncUnitLayouts, JumpBranchLayouts, CommonLayoutFields
from coreblocks.interface.keys import (
    AsyncInterruptInsertSignalKey,
    MispredictionReportKey,
    ExceptionReportKey,
    PredictedJumpTargetKey,
)
from transactron.utils import OneHotSwitch
from transactron.utils.transactron_helpers import make_layout
from coreblocks.func_blocks.interface.func_protocols import FuncUnit
from coreblocks.func_blocks.fu.common.fu_decoder import DecoderManager

__all__ = ["JumpBranchFuncUnit", "JumpComponent"]


log = logging.HardwareLogger("backend.fu.jumpbranch")


class JumpBranchFn(DecoderManager):
    class Fn(IntFlag):
        JAL = auto()
        JALR = auto()
        AUIPC = auto()
        BEQ = auto()
        BNE = auto()
        BLT = auto()
        BLTU = auto()
        BGE = auto()
        BGEU = auto()

    def get_instructions(self) -> Sequence[tuple]:
        return [
            (self.Fn.BEQ, OpType.BRANCH, Funct3.BEQ),
            (self.Fn.BNE, OpType.BRANCH, Funct3.BNE),
            (self.Fn.BLT, OpType.BRANCH, Funct3.BLT),
            (self.Fn.BLTU, OpType.BRANCH, Funct3.BLTU),
            (self.Fn.BGE, OpType.BRANCH, Funct3.BGE),
            (self.Fn.BGEU, OpType.BRANCH, Funct3.BGEU),
            (self.Fn.JAL, OpType.JAL),
            (self.Fn.JALR, OpType.JALR, Funct3.JALR),
            (self.Fn.AUIPC, OpType.AUIPC),
        ]


class JumpBranch(Elaboratable):
    def __init__(self, gen_params: GenParams, fn=JumpBranchFn()):
        self.gen_params = gen_params

        xlen = gen_params.isa.xlen
        self.fn = fn.get_function()
        self.in1 = Signal(xlen)
        self.in2 = Signal(xlen)
        self.in_pc = Signal(xlen)
        self.in_imm = Signal(xlen)
        self.in_rvc = Signal()
        self.jmp_addr = Signal(xlen)
        self.reg_res = Signal(xlen)
        self.taken = Signal()

    def elaborate(self, platform):
        m = Module()

        branch_target = Signal(self.gen_params.isa.xlen)

        # Spec: "The 12-bit B-immediate encodes signed offsets in multiples of 2,
        # and is added to the current pc to give the target address."
        # Multiplies of 2 are converted to the real offset in the decode stage, so we have 13 bits.
        m.d.comb += branch_target.eq(self.in_pc + self.in_imm[:13].as_signed())

        m.d.comb += self.reg_res.eq(self.in_pc + 4)

        if Extension.C in self.gen_params.isa.extensions:
            with m.If(self.in_rvc):
                m.d.comb += self.reg_res.eq(self.in_pc + 2)

        with OneHotSwitch(m, self.fn) as OneHotCase:
            with OneHotCase(JumpBranchFn.Fn.JAL):
                # Spec: "[...] the J-immediate encodes a signed offset in multiples of 2 bytes.
                # The offset is sign-extended and added to the pc to form the jump target address."
                # Multiplies of 2 are converted to the real offset in the decode stage, so we have 21 bits.
                m.d.comb += self.jmp_addr.eq(self.in_pc + self.in_imm[:21].as_signed())
                m.d.comb += self.taken.eq(1)
            with OneHotCase(JumpBranchFn.Fn.JALR):
                # Spec: "The target address is obtained by adding the 12-bit signed I-immediate
                # to the register rs1, then setting the least-significant bit of the result to zero."
                m.d.comb += self.jmp_addr.eq(self.in1 + self.in_imm[:12].as_signed())
                m.d.comb += self.jmp_addr[0].eq(0)
                m.d.comb += self.taken.eq(1)
            with OneHotCase(JumpBranchFn.Fn.AUIPC):
                # Spec: "AUIPC forms a 32-bit offset from the 20-bit U-immediate, filling in the
                # lowest 12 bits with zeros, adds this offset to the pc"
                # Order of arguments in Cat is reversed
                m.d.comb += self.reg_res.eq(self.in_pc + Cat(C(0, 12), self.in_imm[12:]))
            with OneHotCase(JumpBranchFn.Fn.BEQ):
                m.d.comb += self.jmp_addr.eq(branch_target)
                m.d.comb += self.taken.eq(self.in1 == self.in2)
            with OneHotCase(JumpBranchFn.Fn.BNE):
                m.d.comb += self.jmp_addr.eq(branch_target)
                m.d.comb += self.taken.eq(self.in1 != self.in2)
            with OneHotCase(JumpBranchFn.Fn.BLT):
                m.d.comb += self.jmp_addr.eq(branch_target)
                m.d.comb += self.taken.eq(self.in1.as_signed() < self.in2.as_signed())
            with OneHotCase(JumpBranchFn.Fn.BLTU):
                m.d.comb += self.jmp_addr.eq(branch_target)
                m.d.comb += self.taken.eq(self.in1.as_unsigned() < self.in2.as_unsigned())
            with OneHotCase(JumpBranchFn.Fn.BGE):
                m.d.comb += self.jmp_addr.eq(branch_target)
                m.d.comb += self.taken.eq(self.in1.as_signed() >= self.in2.as_signed())
            with OneHotCase(JumpBranchFn.Fn.BGEU):
                m.d.comb += self.jmp_addr.eq(branch_target)
                m.d.comb += self.taken.eq(self.in1.as_unsigned() >= self.in2.as_unsigned())

        return m


class JumpBranchFuncUnit(FuncUnit, Elaboratable):
    def __init__(self, gen_params: GenParams, jb_fn=JumpBranchFn()):
        self.gen_params = gen_params

        layouts = gen_params.get(FuncUnitLayouts)

        self.issue = Method(i=layouts.issue)
        self.accept = Method(o=layouts.accept)

        self.jb_fn = jb_fn

        self.perf_instr = TaggedCounter(
            "backend.fu.jumpbranch.instr",
            "Counts of instructions executed by the jumpbranch unit",
            tags=JumpBranchFn.Fn,
        )
        self.perf_misaligned = HwCounter(
            "backend.fu.jumpbranch.misaligned", "Number of instructions with misaligned target address"
        )
        self.perf_mispredictions = HwCounter("backend.fu.jumpbranch.mispredictions", "Number of branch mispredictions")

    def elaborate(self, platform):
        m = TModule()

        m.submodules += [
            self.perf_instr,
            self.perf_misaligned,
            self.perf_mispredictions,
        ]

        dm = DependencyContext.get()
        jump_target_req, jump_target_resp = dm.get_dependency(PredictedJumpTargetKey())

        m.submodules.jb = jb = JumpBranch(self.gen_params, fn=self.jb_fn)
        m.submodules.decoder = decoder = self.jb_fn.get_decoder(self.gen_params)

        fields = self.gen_params.get(CommonLayoutFields)
        instr_fifo_layout = make_layout(
            fields.rob_id,
            fields.pc,
            fields.rp_dst,
            ("type", JumpBranchFn.Fn),
            ("jmp_addr", self.gen_params.isa.xlen),
            ("reg_res", self.gen_params.isa.xlen),
            ("taken", 1),
            fields.predicted_taken,
            fields.ftq_addr,
        )
        m.submodules.instr_fifo = instr_fifo = BasicFifo(instr_fifo_layout, 2)

        @def_method(m, self.accept)
        def _():
            instr = instr_fifo.read(m)
            prediction = jump_target_resp(m)

            jump_result = Mux(instr.taken, instr.jmp_addr, instr.reg_res)
            is_auipc = instr.type == JumpBranchFn.Fn.AUIPC

            predicted_addr_correctly = (instr.type != JumpBranchFn.Fn.JALR) | (
                prediction.maybe_cfi_target.valid & (prediction.maybe_cfi_target.value == instr.jmp_addr)
            )

            misprediction = Signal()
            m.d.av_comb += misprediction.eq(
                ~(is_auipc | (predicted_addr_correctly & (instr.taken == instr.predicted_taken)))
            )
            self.perf_mispredictions.incr(m, cond=misprediction)

            jmp_addr_misaligned = (
                instr.jmp_addr & (0b1 if Extension.C in self.gen_params.isa.extensions else 0b11)
            ) != 0

            async_interrupt_active = dm.get_dependency(AsyncInterruptInsertSignalKey())
            exception_report = dm.get_dependency(ExceptionReportKey())
            misprediction_report = dm.get_dependency(MispredictionReportKey())

            exception = Signal()

            with m.If(~is_auipc & instr.taken & jmp_addr_misaligned):
                self.perf_misaligned.incr(m)
                # Spec: "[...] if the target address is not four-byte aligned. This exception is reported on the branch
                # or jump instruction, not on the target instruction. No instruction-address-misaligned exception is
                # generated for a conditional branch that is not taken."
                m.d.comb += exception.eq(1)
                exception_report(
                    m, rob_id=instr.rob_id, cause=ExceptionCause.INSTRUCTION_ADDRESS_MISALIGNED, pc=instr.pc
                )
            with m.Elif(async_interrupt_active & ~is_auipc):
                # Jump instructions are entry points for async interrupts.
                # This way we can store known pc via report to global exception register and avoid it in ROB.
                # Exceptions have priority, because the instruction that reports async interrupt is commited
                # and exception would be lost.
                m.d.comb += exception.eq(1)
                exception_report(
                    m, rob_id=instr.rob_id, cause=ExceptionCause._COREBLOCKS_ASYNC_INTERRUPT, pc=jump_result
                )
            with m.Elif(misprediction):
                # Async interrupts can have priority, because `jump_result` is handled in the same way.
                # No extra misprediction penalty will be introducted at interrupt return to `jump_result` address.
                m.d.comb += exception.eq(1)
                exception_report(m, rob_id=instr.rob_id, cause=ExceptionCause._COREBLOCKS_MISPREDICTION, pc=jump_result)

                misprediction_report(m, ftq_addr=instr.ftq_addr, cfi_target=jump_result)

            return {
                "rob_id": instr.rob_id,
                "result": instr.reg_res,
                "rp_dst": instr.rp_dst,
                "exception": exception,
            }

        @def_method(m, self.issue)
        def _(arg):
            m.d.top_comb += decoder.exec_fn.eq(arg.exec_fn)
            m.d.top_comb += jb.fn.eq(decoder.decode_fn)

            m.d.top_comb += jb.in1.eq(arg.s1_val)
            m.d.top_comb += jb.in2.eq(arg.s2_val)
            m.d.top_comb += jb.in_pc.eq(arg.pc)
            m.d.top_comb += jb.in_imm.eq(arg.imm)

            funct7_info = Signal(from_method_layout(self.gen_params.get(JumpBranchLayouts).funct7_info))
            m.d.top_comb += funct7_info.eq(arg.exec_fn.funct7)
            m.d.top_comb += jb.in_rvc.eq(funct7_info.rvc)

            jump_target_req(m, ftq_idx=arg.ftq_addr.ftq_idx)

            instr_fifo.write(
                m,
                rob_id=arg.rob_id,
                pc=arg.pc,
                rp_dst=arg.rp_dst,
                type=decoder.decode_fn,
                jmp_addr=jb.jmp_addr,
                reg_res=jb.reg_res,
                taken=jb.taken,
                predicted_taken=funct7_info.predicted_taken,
                ftq_addr=arg.ftq_addr,
            )
            self.perf_instr.incr(m, decoder.decode_fn)

        return m


class JumpComponent(FunctionalComponentParams):
    def __init__(self):
        self.jb_fn = JumpBranchFn()

    def get_module(self, gen_params: GenParams) -> FuncUnit:
        unit = JumpBranchFuncUnit(gen_params, self.jb_fn)
        return unit

    def get_optypes(self) -> set[OpType]:
        return self.jb_fn.get_op_types()
