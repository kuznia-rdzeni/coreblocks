from enum import IntEnum, unique

from amaranth import *

from coreblocks.isa import OpType, Funct3, Funct7
from coreblocks.transactions import *
from coreblocks.transactions.core import def_method
from coreblocks.transactions.lib import *

from coreblocks.genparams import GenParams
from coreblocks.layouts import *


class MulFn(Signal):
    @unique
    class Fn(IntEnum):
        MUL = 1 << 0     # Lower part multiplication
        MULH = 1 << 1    # Upper part multiplication signed×signed
        MULHU = 1 << 2   # Upper part multiplication unsigned×unsigned
        MULHSU = 1 << 3  # Upper part multiplication signed×unsigned
        MULW = 1 << 4    # Multiplication of lower half of bits

    def __init__(self, *args, **kwargs):
        super().__init__(MulFn.Fn, *args, **kwargs)


class MulFnDecoder(Elaboratable):
    def __init__(self, gen: GenParams):
        layouts = gen.get(CommonLayouts)

        self.exec_fn = Record(layouts.exec_fn)
        self.mul_fn = Signal(MulFn.Fn)

    def elaborate(self, platform):
        m = Module()

        ops = [
            (MulFn.Fn.MUL, OpType.ARITHMETIC, Funct3.MUL, Funct7.MULDIV),
            (MulFn.Fn.MULH, OpType.ARITHMETIC, Funct3.MULH, Funct7.MULDIV),
            (MulFn.Fn.MULHU, OpType.ARITHMETIC, Funct3.MULHU, Funct7.MULDIV),
            (MulFn.Fn.MULHSU, OpType.ARITHMETIC, Funct3.MULHSU, Funct7.MULDIV),
            (MulFn.Fn.MULW, OpType.ARITHMETIC_W, Funct3.MULW, Funct7.MULDIV),
        ]

        for op in ops:
            cond = (self.exec_fn.op_type == op[1]) & (self.exec_fn.funct3 == op[2]) & (self.exec_fn.funct7 == op[3])

            with m.If(cond):
                m.d.comb += self.mul_fn.eq(op[0])

        return m


class MulBaseUnsigned(Elaboratable):
    def __init__(self, gen: GenParams):
        self.gen = gen

        self.issue = Method(i=[("i1", gen.isa.xlen), ("i2", gen.isa.xlen)])
        self.accept = Method(o=[("o", gen.isa.xlen * 2)])

    def elaborate(self, platform):
        m = Module()
        res = Signal(unsigned(self.gen.isa.xlen * 2))

        i1 = Signal(unsigned(self.gen.isa.xlen * 2))
        i2 = Signal(unsigned(self.gen.isa.xlen))
        accepted = Signal(1, reset=1)

        m.submodules.mul = mul = FastRecursiveMul(self.gen.isa.xlen)

        @def_method(m, self.issue, ready=accepted)
        def _(arg):
            m.d.sync += i1.eq(arg.i1)
            m.d.sync += i2.eq(arg.i2)

            m.d.sync += accepted.eq(0)

        @def_method(m, self.accept, ready=(~accepted))
        def _(arg):
            m.d.comb += mul.i1.eq(i1)
            m.d.comb += mul.i2.eq(i2)
            m.d.comb += res.eq(mul.r)
            m.d.sync += accepted.eq(1)
            return {"o": res}

        return m


class FastRecursiveMul(Elaboratable):
    def __init__(self, n):
        self.n = n

        self.i1 = Signal(unsigned(n))
        self.i2 = Signal(unsigned(n))
        self.r = Signal(unsigned(n * 2))

    def elaborate(self, platform):
        m = Module()
        if self.n == 1:
            m.d.comb += self.r.eq(self.i1 & self.i2)
        elif self.n == 2:
            m.d.comb += self.r.eq(((self.i1[1] & self.i2[1]) << 2) +
                                  (((self.i1[0] & self.i2[1]) + (self.i1[1] & self.i2[0])) << 1) +
                                  (self.i1[0] & self.i2[0]))
        elif self.n == 3:
            m.submodules.low_mul = low_mul = FastRecursiveMul(2)
            signal_low = Signal(unsigned(4))
            m.d.comb += low_mul.i1.eq(self.i1[:2])
            m.d.comb += low_mul.i2.eq(self.i2[:2])
            m.d.comb += signal_low.eq(low_mul.r)

            m.d.comb += self.r.eq(((self.i1[2] & self.i2[2]) << 4) +
                                  ((Mux(self.i1[2], self.i2[:2], 0) + Mux(self.i2[2], self.i1[:2], 0)) << 2) +
                                  signal_low)

            m.d.comb += self.r.eq(self.i1 * self.i2)
        else:
            upper = self.n // 2
            lower = (self.n + 1) // 2
            m.submodules.low_mul = low_mul = FastRecursiveMul(lower)
            m.submodules.mid_mul = mid_mul = FastRecursiveMul(lower + 1)
            m.submodules.upper_mul = upper_mul = FastRecursiveMul(upper)

            signal_low = Signal(unsigned(2 * lower))
            signal_mid = Signal(unsigned(2 * lower + 2))
            signal_upper = Signal(unsigned(2 * upper))

            m.d.comb += low_mul.i1.eq(self.i1[:lower])
            m.d.comb += low_mul.i2.eq(self.i2[:lower])
            m.d.comb += signal_low.eq(low_mul.r)

            m.d.comb += mid_mul.i1.eq(self.i1[:lower] + self.i1[lower:])
            m.d.comb += mid_mul.i2.eq(self.i2[:lower] + self.i2[lower:])
            m.d.comb += signal_mid.eq(mid_mul.r)

            m.d.comb += upper_mul.i1.eq(self.i1[lower:])
            m.d.comb += upper_mul.i2.eq(self.i2[lower:])
            m.d.comb += signal_upper.eq(upper_mul.r)

            m.d.comb += self.r.eq(signal_low + ((signal_mid - signal_low - signal_upper) << lower) +
                                  (signal_upper << 2 * lower))

        return m


class ShiftUnsignedMul(MulBaseUnsigned):
    def __init__(self, gen: GenParams):
        super().__init__(gen)

    def elaborate(self, platform):
        m = Module()
        res = Signal(unsigned(self.gen.isa.xlen * 2))

        i1 = Signal(unsigned(self.gen.isa.xlen * 2))
        i2 = Signal(unsigned(self.gen.isa.xlen))
        accepted = Signal(1, reset=1)

        @def_method(m, self.issue, ready=accepted)
        def _(arg):
            m.d.sync += res.eq(0)
            m.d.sync += i1.eq(arg.i1)
            m.d.sync += i2.eq(arg.i2)
            m.d.sync += accepted.eq(0)

        @def_method(m, self.accept, ready=(~i2.bool() & ~accepted))
        def _(arg):
            m.d.sync += accepted.eq(1)
            return {"o": res}

        with m.If(~accepted):
            with m.If(i2[0]):
                m.d.sync += res.eq(res + i1)
            m.d.sync += i1.eq(i1 << 1)
            m.d.sync += i2.eq(i2 >> 1)

        return m


class MulUnit(Elaboratable):
    def __init__(self, gen: GenParams):
        self.gen = gen

        layouts = gen.get(FuncUnitLayouts)

        self.issue = Method(i=layouts.issue)
        self.accept = Method(o=layouts.accept)

    def elaborate(self, platform):
        m = Module()

        m.submodules.fifo = fifo = FIFO(self.gen.get(FuncUnitLayouts).accept, 2)
        m.submodules.decoder = decoder = MulFnDecoder(self.gen)
        m.submodules.multiplier = multiplier = ShiftUnsignedMul(self.gen)

        accepted = Signal(1, reset=1)

        rob_id = Signal(self.gen.rob_entries_bits)
        rp_dst = Signal(self.gen.phys_regs_bits)
        value1 = Signal(self.gen.isa.xlen)
        value2 = Signal(self.gen.isa.xlen)
        negative_res = Signal(1)
        high_res = Signal(1)

        xlen = self.gen.isa.xlen
        sign_bit = xlen - 1
        half_sign_bit = xlen // 2 - 1

        @def_method(m, self.accept)
        def _(arg):
            return fifo.read(m)

        @def_method(m, self.issue, ready=accepted)
        def _(arg):
            m.d.sync += rob_id.eq(arg.rob_id)
            m.d.sync += rp_dst.eq(arg.rp_dst)
            m.d.comb += decoder.exec_fn.eq(arg.exec_fn)
            i1 = arg.s1_val
            i2 = Mux(arg.imm, arg.imm, arg.s2_val)

            with m.Switch(decoder.mul_fn):
                with m.Case(MulFn.Fn.MUL):
                    m.d.sync += negative_res.eq(0)
                    m.d.sync += high_res.eq(0)
                    m.d.comb += value1.eq(i1)
                    m.d.comb += value2.eq(i2)
                with m.Case(MulFn.Fn.MULH):
                    m.d.sync += negative_res.eq(i1[sign_bit] ^ i2[sign_bit])
                    m.d.sync += high_res.eq(1)
                    m.d.comb += value1.eq(Mux(i1[sign_bit], -i1, i1))
                    m.d.comb += value2.eq(Mux(i2[sign_bit], -i2, i2))
                with m.Case(MulFn.Fn.MULHU):
                    m.d.sync += negative_res.eq(0)
                    m.d.sync += high_res.eq(1)
                    m.d.comb += value1.eq(i1)
                    m.d.comb += value2.eq(i2)
                with m.Case(MulFn.Fn.MULHSU):
                    m.d.sync += negative_res.eq(i1[sign_bit])
                    m.d.sync += high_res.eq(1)
                    m.d.comb += value1.eq(Mux(i1[sign_bit], -i1, i1))
                    m.d.comb += value2.eq(i2)
                with m.Case(MulFn.Fn.MULW):
                    m.d.sync += negative_res.eq(i1[half_sign_bit] ^ i2[half_sign_bit])
                    m.d.sync += high_res.eq(0)
                    i1h = Signal(xlen // 2)
                    i2h = Signal(xlen // 2)
                    m.d.comb += i1h.eq(Mux(i1[half_sign_bit], -i1, i1))
                    m.d.comb += i2h.eq(Mux(i2[half_sign_bit], -i2, i2))
                    m.d.comb += value1.eq(i1h)
                    m.d.comb += value2.eq(i2h)

                multiplier.issue(m, {"i1": value1, "i2": value2})
            m.d.sync += accepted.eq(0)

        with Transaction().body(m):
            response = multiplier.accept(m)
            sign_result = Mux(negative_res, -response.o, response.o)
            result = Mux(high_res, sign_result[xlen:], sign_result[:xlen])

            fifo.write(m, arg={"rob_id": rob_id, "result": result, "rp_dst": rp_dst})
            m.d.sync += accepted.eq(1)

        return m
