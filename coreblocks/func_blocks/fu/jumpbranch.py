from amaranth import *

from enum import IntFlag, auto

from typing import Sequence

from transactron import *
from transactron.core import def_method
from transactron.lib import *
from transactron.lib import logging
from transactron.utils import DependencyManager
from coreblocks.params import GenParams, FunctionalComponentParams, Extension
from coreblocks.frontend.decoder import Funct3, OpType, ExceptionCause
from coreblocks.interface.layouts import FuncUnitLayouts, JumpBranchLayouts
from coreblocks.interface.keys import AsyncInterruptInsertSignalKey, BranchVerifyKey, ExceptionReportKey
from transactron.utils import OneHotSwitch
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

        self.fifo_branch_resolved = FIFO(self.gen_params.get(JumpBranchLayouts).verify_branch, 2)

        self.jb_fn = jb_fn

        self.dm = gen_params.get(DependencyManager)
        self.dm.add_dependency(BranchVerifyKey(), self.fifo_branch_resolved.read)

        self.perf_jumps = HwCounter("backend.fu.jumpbranch.jumps", "Number of jump instructions issued")
        self.perf_branches = HwCounter("backend.fu.jumpbranch.branches", "Number of branch instructions issued")
        self.perf_misaligned = HwCounter(
            "backend.fu.jumpbranch.misaligned", "Number of instructions with misaligned target address"
        )

    def elaborate(self, platform):
        m = TModule()

        m.submodules += [self.perf_jumps, self.perf_branches, self.perf_misaligned]

        m.submodules.jb = jb = JumpBranch(self.gen_params, fn=self.jb_fn)
        m.submodules.fifo_res = fifo_res = FIFO(self.gen_params.get(FuncUnitLayouts).accept, 2)
        m.submodules.decoder = decoder = self.jb_fn.get_decoder(self.gen_params)
        m.submodules.fifo_branch_resolved = self.fifo_branch_resolved

        @def_method(m, self.accept)
        def _():
            return fifo_res.read(m)

        @def_method(m, self.issue)
        def _(arg):
            m.d.top_comb += decoder.exec_fn.eq(arg.exec_fn)
            m.d.top_comb += jb.fn.eq(decoder.decode_fn)

            m.d.top_comb += jb.in1.eq(arg.s1_val)
            m.d.top_comb += jb.in2.eq(arg.s2_val)
            m.d.top_comb += jb.in_pc.eq(arg.pc)
            m.d.top_comb += jb.in_imm.eq(arg.imm)

            m.d.top_comb += jb.in_rvc.eq(arg.exec_fn.funct7)

            is_auipc = decoder.decode_fn == JumpBranchFn.Fn.AUIPC
            is_jump = (decoder.decode_fn == JumpBranchFn.Fn.JAL) | (decoder.decode_fn == JumpBranchFn.Fn.JALR)

            jump_result = Mux(jb.taken, jb.jmp_addr, jb.reg_res)

            self.perf_jumps.incr(m, cond=is_jump)
            self.perf_branches.incr(m, cond=(~is_jump & ~is_auipc))

            exception = Signal()
            exception_report = self.dm.get_dependency(ExceptionReportKey())

            jmp_addr_misaligned = (jb.jmp_addr & (0b1 if Extension.C in self.gen_params.isa.extensions else 0b11)) != 0

            async_interrupt_active = self.gen_params.get(DependencyManager).get_dependency(
                AsyncInterruptInsertSignalKey()
            )

            # TODO: Update with branch prediction support.
            # Temporarily there is no jump prediction, jumps don't stall fetch and pc+4 is always fetched to pipeline
            misprediction = ~is_auipc & jb.taken

            with m.If(~is_auipc & jb.taken & jmp_addr_misaligned):
                self.perf_misaligned.incr(m)
                # Spec: "[...] if the target address is not four-byte aligned. This exception is reported on the branch
                # or jump instruction, not on the target instruction. No instruction-address-misaligned exception is
                # generated for a conditional branch that is not taken."
                m.d.comb += exception.eq(1)
                exception_report(m, rob_id=arg.rob_id, cause=ExceptionCause.INSTRUCTION_ADDRESS_MISALIGNED, pc=arg.pc)
            with m.Elif(async_interrupt_active & ~is_auipc):
                # Jump instructions are entry points for async interrupts.
                # This way we can store known pc via report to global exception register and avoid it in ROB.
                # Exceptions have priority, because the instruction that reports async interrupt is commited
                # and exception would be lost.
                m.d.comb += exception.eq(1)
                exception_report(m, rob_id=arg.rob_id, cause=ExceptionCause._COREBLOCKS_ASYNC_INTERRUPT, pc=jump_result)
            with m.Elif(misprediction):
                # Async interrupts can have priority, because `jump_result` is handled in the same way.
                # No extra misprediction penalty will be introducted at interrupt return to `jump_result` address.
                m.d.comb += exception.eq(1)
                exception_report(m, rob_id=arg.rob_id, cause=ExceptionCause._COREBLOCKS_MISPREDICTION, pc=jump_result)

            fifo_res.write(m, rob_id=arg.rob_id, result=jb.reg_res, rp_dst=arg.rp_dst, exception=exception)

            with m.If(~is_auipc):
                self.fifo_branch_resolved.write(m, from_pc=jb.in_pc, next_pc=jump_result, misprediction=misprediction)
                log.debug(
                    m,
                    True,
                    "jumping from 0x{:08x} to 0x{:08x}; misprediction: {}",
                    jb.in_pc,
                    jump_result,
                    misprediction,
                )

        return m


class JumpComponent(FunctionalComponentParams):
    def __init__(self):
        self.jb_fn = JumpBranchFn()

    def get_module(self, gen_params: GenParams) -> FuncUnit:
        unit = JumpBranchFuncUnit(gen_params, self.jb_fn)
        return unit

    def get_optypes(self) -> set[OpType]:
        return self.jb_fn.get_op_types()
