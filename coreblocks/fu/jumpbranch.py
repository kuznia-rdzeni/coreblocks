from amaranth import *

from enum import IntFlag, auto

from typing import Sequence

from coreblocks.transactions import *
from coreblocks.transactions.core import def_method
from coreblocks.transactions.lib import *

from coreblocks.params import *
from coreblocks.utils import OneHotSwitch
from coreblocks.utils.protocols import FuncUnit

from coreblocks.fu.fu_decoder import DecoderManager

__all__ = ["JumpBranchFuncUnit", "JumpComponent"]


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
    def __init__(self, gen: GenParams, verify_branch: Method, jb_fn=JumpBranchFn()):
        self.gen = gen

        layouts = gen.get(FuncUnitLayouts)

        self.issue = Method(i=layouts.issue)
        self.accept = Method(o=layouts.accept)

        self.jb_fn = jb_fn
        self.verify_branch = verify_branch

    def elaborate(self, platform):
        m = TModule()

        m.submodules.jb = jb = JumpBranch(self.gen, fn=self.jb_fn)
        m.submodules.fifo_res = fifo_res = FIFO(self.gen.get(FuncUnitLayouts).accept, 2)
        m.submodules.decoder = decoder = self.jb_fn.get_decoder(self.gen)

        @def_method(m, self.accept)
        def _():
            return fifo_res.read(m)

        @def_method(m, self.issue)
        def _(arg):
            next_pc = Signal(self.gen.isa.xlen)
            exception = Signal()

            m.d.comb += decoder.exec_fn.eq(arg.exec_fn)
            m.d.comb += jb.fn.eq(decoder.decode_fn)

            m.d.comb += jb.in1.eq(arg.s1_val)
            m.d.comb += jb.in2.eq(arg.s2_val)
            m.d.comb += jb.in_pc.eq(arg.pc)
            m.d.comb += jb.in_imm.eq(arg.imm)

            m.d.comb += next_pc.eq(Mux(jb.taken, jb.jmp_addr, jb.reg_res))

            # skip writing next branch target for auipc
            with m.If(decoder.decode_fn != JumpBranchFn.Fn.AUIPC):
                verify = self.verify_branch(m, from_pc=jb.in_pc, next_pc=next_pc)
                m.d.comb += exception.eq(verify["mispredict"])

            fifo_res.write(m, rob_id=arg.rob_id, result=jb.reg_res, rp_dst=arg.rp_dst, exception=exception)

        return m


class JumpComponent(FunctionalComponentParams):
    def __init__(self):
        self.jb_fn = JumpBranchFn()

    def get_module(self, gen_params: GenParams) -> FuncUnit:
        connections = gen_params.get(DependencyManager)
        verify_branch = connections.get_dependency(VerifyBranchKey())
        unit = JumpBranchFuncUnit(gen_params, verify_branch, self.jb_fn)
        return unit

    def get_optypes(self) -> set[OpType]:
        return self.jb_fn.get_op_types()
