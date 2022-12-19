from amaranth import *

from enum import IntEnum, unique

from coreblocks.transactions import *
from coreblocks.transactions.core import def_method
from coreblocks.transactions.lib import *

from coreblocks.params import *

__all__ = ["JumpBranchUnit"]


class JumpBranchFn(Signal):
    @unique
    class Fn(IntEnum):
        JAL = 1 << 0
        JALR = 1 << 1
        BEQ = 1 << 2
        BNE = 1 << 3
        BLT = 1 << 4
        BLTU = 1 << 5
        BGE = 1 << 6
        BGEU = 1 << 7

    def __init__(self, *args, **kwargs):
        super().__init__(JumpBranchFn.Fn, *args, **kwargs)


class JumpBranch(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params

        xlen = gen_params.isa.xlen
        self.fn = JumpBranchFn()
        self.in1 = Signal(xlen)
        self.in2 = Signal(xlen)
        self.in_pc = Signal(xlen)
        self.in_imm = Signal(xlen)
        self.jmp_addr = Signal(xlen)
        self.ret_addr = Signal(xlen)
        self.taken = Signal()

    def elaborate(self, platform):
        m = Module()

        m.d.comb += self.ret_addr.eq(self.in_pc + 4)

        # Spec: "The 12-bit B-immediate encodes signed offsets in multiples of 2,
        # and is added to the current pc to give the target address."
        branch_target = self.in_pc + self.in_imm[:12].as_signed()

        with OneHotSwitch(m, self.fn) as OneHotCase:
            with OneHotCase(JumpBranchFn.Fn.JAL):
                # Spec: "[...] the J-immediate encodes a signed offset in multiples of 2 bytes.
                # The offset is sign-extended and added to the pc to form the jump target address."
                m.d.comb += self.jmp_addr.eq(self.in_pc + self.in_imm[:20].as_signed())
                m.d.comb += self.taken.eq(1)
            with OneHotCase(JumpBranchFn.Fn.JALR):
                # Spec: "The target address is obtained by adding the 12-bit signed I-immediate
                # to the register rs1, then setting the least-significant bit of the result to zero."
                target = self.in1 + self.in_imm[:12].as_signed()
                m.d.comb += self.jmp_addr.eq(target)
                m.d.comb += self.jmp_addr[0].eq(0)
                m.d.comb += self.taken.eq(1)
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

        # so that Amaranth allows us to use add_clock
        dummy = Signal()
        m.d.sync += dummy.eq(1)

        return m


class JumpBranchFnDecoder(Elaboratable):
    def __init__(self, gen: GenParams):
        layouts = gen.get(CommonLayouts)

        self.exec_fn = Record(layouts.exec_fn) # TODO: extended layout with PC
        self.jb_fn = Signal(JumpBranchFn.Fn)

    def elaborate(self, platform):
        m = Module()

        ops = [
            (JumpBranchFn.Fn.BEQ, OpType.BRANCH, Funct3.BEQ),
            (JumpBranchFn.Fn.BNE, OpType.BRANCH, Funct3.BNE),
            (JumpBranchFn.Fn.BLT, OpType.BRANCH, Funct3.BLT),
            (JumpBranchFn.Fn.BLTU, OpType.BRANCH, Funct3.BLTU),
            (JumpBranchFn.Fn.BGE, OpType.BRANCH, Funct3.BGE),
            (JumpBranchFn.Fn.BGEU, OpType.BRANCH, Funct3.BGEU),
            (JumpBranchFn.Fn.JAL, OpType.JAL),
            (JumpBranchFn.Fn.JALR, OpType.JALR, Funct3.JALR),
        ]

        for op in ops:
            cond = (self.exec_fn.op_type == op[1]) & (self.exec_fn.funct3 == op[2] if len(op) > 2 else 1)

            with m.If(cond):
                m.d.comb += self.jb_fn.eq(op[0])

        return m


