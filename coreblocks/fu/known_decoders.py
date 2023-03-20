from amaranth import *

from coreblocks.transactions import *
from coreblocks.transactions.core import def_method
from coreblocks.transactions.lib import *

from coreblocks.params import *
from coreblocks.utils import OneHotSwitch

from coreblocks.utils.protocols import FuncUnit

# 4 decoders in use


class AluFnDecoder(Elaboratable):
    def __init__(self, gen: GenParams):
        layouts = gen.get(CommonLayouts)

        self.exec_fn = Record(layouts.exec_fn)
        self.alu_fn = Signal(AluFn.Fn)

    def elaborate(self, platform):
        m = Module()

        ops = [
            (AluFn.Fn.ADD, OpType.ARITHMETIC, Funct3.ADD, Funct7.ADD),
            (AluFn.Fn.SUB, OpType.ARITHMETIC, Funct3.ADD, Funct7.SUB),
            (AluFn.Fn.SLT, OpType.COMPARE, Funct3.SLT),
            (AluFn.Fn.SLTU, OpType.COMPARE, Funct3.SLTU),
            (AluFn.Fn.XOR, OpType.LOGIC, Funct3.XOR),
            (AluFn.Fn.OR, OpType.LOGIC, Funct3.OR),
            (AluFn.Fn.AND, OpType.LOGIC, Funct3.AND),
            (AluFn.Fn.SLL, OpType.SHIFT, Funct3.SLL),
            (AluFn.Fn.SRL, OpType.SHIFT, Funct3.SR, Funct7.SL),
            (AluFn.Fn.SRA, OpType.SHIFT, Funct3.SR, Funct7.SA),
            (AluFn.Fn.SH1ADD, OpType.ADDRESS_GENERATION, Funct3.SH1ADD, Funct7.SH1ADD),
            (AluFn.Fn.SH2ADD, OpType.ADDRESS_GENERATION, Funct3.SH2ADD, Funct7.SH2ADD),
            (AluFn.Fn.SH3ADD, OpType.ADDRESS_GENERATION, Funct3.SH3ADD, Funct7.SH3ADD),
        ]

        for op in ops:
            cond = (self.exec_fn.op_type == op[1]) & (self.exec_fn.funct3 == op[2])
            if len(op) == 4:
                cond = cond & (self.exec_fn.funct7 == op[3])

            with m.If(cond):
                m.d.comb += self.alu_fn.eq(op[0])

        return m


class JumpBranchFnDecoder(Elaboratable):
    def __init__(self, gen: GenParams):
        layouts = gen.get(CommonLayouts)

        self.exec_fn = Record(layouts.exec_fn)
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
            (JumpBranchFn.Fn.AUIPC, OpType.AUIPC),
        ]

        for op in ops:
            cond = (self.exec_fn.op_type == op[1]) & (self.exec_fn.funct3 == op[2] if len(op) > 2 else 1)

            with m.If(cond):
                m.d.comb += self.jb_fn.eq(op[0])

        return m


class ZbsFunctionDecoder(Elaboratable):
    """
    Module decoding function into hot wired ZbsFunction.

    Attributes
    ----------
    exec_fn: Record(CommonLayouts.exec_fn), in
        Function to be decoded.
    zbs_function: ZbsFunction, out
        Function decoded into OneHotWire output.
    """

    def __init__(self, gen: GenParams):
        """
        Parameters
        ----------
        gen: GenParams
            Core generation parameters.
        """
        layouts = gen.get(CommonLayouts)

        self.exec_fn = Record(layouts.exec_fn)
        self.zbs_function = Signal(ZbsFunction.Function)

    def elaborate(self, platform):
        m = Module()

        # Type errors ignored because of using `Value._as_const()`, an internal, undocumented
        # function. Amaranth doesn't support `Cat` as an argument of `Module.Case`.
        # Discussion: https://github.com/kuznia-rdzeni/coreblocks/pull/194#issuecomment-1407378082
        with m.Switch(Cat(self.exec_fn.funct3, self.exec_fn.funct7)):
            with m.Case(Cat(Funct3.BCLR, Funct7.BCLR)._as_const()):  # type: ignore
                m.d.comb += self.zbs_function.eq(ZbsFunction.Function.BCLR)
            with m.Case(Cat(Funct3.BEXT, Funct7.BEXT)._as_const()):  # type: ignore
                m.d.comb += self.zbs_function.eq(ZbsFunction.Function.BEXT)
            with m.Case(Cat(Funct3.BINV, Funct7.BINV)._as_const()):  # type: ignore
                m.d.comb += self.zbs_function.eq(ZbsFunction.Function.BINV)
            with m.Case(Cat(Funct3.BSET, Funct7.BSET)._as_const()):  # type: ignore
                m.d.comb += self.zbs_function.eq(ZbsFunction.Function.BSET)

        return m


class MulFnDecoder(Elaboratable):
    """
    Module decoding function into hot wired MulFn.

    Attributes
    ----------
    exec_fn: Record(gen.get(CommonLayouts).exec_fn), in
        Function to be decoded.
    mul_fn: MulFn, out
        Function decoded into OneHotWire output.
    """

    def __init__(self, gen: GenParams):
        """
        Parameters
        ----------
        gen: GenParams
            Core generation parameters.
        """
        layouts = gen.get(CommonLayouts)

        self.exec_fn = Record(layouts.exec_fn)
        self.mul_fn = MulFn()

    def elaborate(self, platform):
        m = Module()

        with m.Switch(self.exec_fn.funct3):
            with m.Case(Funct3.MUL):
                m.d.comb += self.mul_fn.eq(MulFn.Fn.MUL)
            with m.Case(Funct3.MULH):
                m.d.comb += self.mul_fn.eq(MulFn.Fn.MULH)
            with m.Case(Funct3.MULHU):
                m.d.comb += self.mul_fn.eq(MulFn.Fn.MULHU)
            with m.Case(Funct3.MULHSU):
                m.d.comb += self.mul_fn.eq(MulFn.Fn.MULHSU)
        # Prepared for RV64
        #
        # with m.If(self.exec_fn.op_type == OpType.ARITHMETIC_W):
        #     m.d.comb += self.mul_fn.eq(MulFn.Fn.MULW)

        return m
