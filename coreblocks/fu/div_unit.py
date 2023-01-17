from amaranth import *
from enum import unique
from coreblocks.params import GenParams, CommonLayouts, Funct3, FuncUnitLayouts
from coreblocks.transactions.core import def_method
from coreblocks.transactions.lib import FIFO
from coreblocks.fu.division.long import LongDivider
from coreblocks.utils import OneHotSwitch

__all__ = ["DivUnit", "DivFn"]


class DivFn(Signal):
    @unique
    class Fn(Signal):
        DIV = 1 << 0
        DIVU = 1 << 1
        REM = 1 << 2
        REMU = 1 << 3

    def __init__(self, *args, **kwargs):
        super().__init__(MulFn.Fn, *args, **kwargs)


class DivFnDecoder(Elaboratable):
    def __init__(self, gen: GenParams):
        layouts = gen.get(CommonLayouts)
        self.exec_fn = Record(layouts.exec_fn)
        self.div_fn = DivFn()

    def elaborate(self, platform):
        m = Module()

        with m.Switch(self.exec_fn.funct3):
            with m.Case(Funct3.DIV):
                m.d.comb += self.div_fn.eq(DivFn.Fn.DIV)
            with m.Case(Funct3.DIVU):
                m.d.comb += self.div_fn.eq(DivFn.Fn.DIVU)
            with m.Case(Funct3.REM):
                m.d.comb += self.div_fn.eq(DivFn.Fn.REM)
            with m.Case(Funct3.REMU):
                m.d.comb += self.div_fn.eq(DivFn.Fn.REMU)
        return m


class DivUnit(Elaboratable):
    def __init__(self, gen: GenParams):
        self.gen = gen

        layouts = gen.get(FuncUnitLayouts)

        self.issue = Method(i=layouts.issue)
        self.accept = Method(o=layouts.accept)

    def elaborate(self, platform):
        m = Module()

        m.submodules.result_fifo = result_fifo = FIFO(self.gen.get(FuncUnitLayouts).accept, 2)
        m.submodules.params_fifo = params_fifo = FIFO(
            [
                ("rob_id", self.gen.rob_entries_bits),
                ("rp_dst", self.gen.phys_regs_bits),
            ],
            2,
        )

        m.submodules.decoder = decoder = DivFnDecoder(self.gen)

        m.submodules.divider = LongDivider(self.gen)

        @def_method(m, self.accept)
        def _(arg):
            return result_fifo.read(m)

        @def_method(m, self.issue)
        def _(arg):
            m.d.comb += decoder.exec_fn.eq(arg.exec_fn)

            arg1, arg2 = arg.s1_val, Mux(arg.imm, arg.imm, arg.s2_val)

            dividend = Signal(self.gen.isa.xlen)
            divisor = Signal(self.gen.isa.xlen)

            with OneHotSwitch(m, decoder.div_fn) as OneHotCase:
                with OneHotCase(DivFn.Fn.DIV):
                    m.d.comb += dividend.eq(arg1)
                    m.d.comb += divisor.eq(arg2)
                with OneHotCase(DivFn.Fn.DIVU):
                    pass
                with OneHotCase(DivFn.Fn.REM):
                    pass
                with OneHotCase(DivFn.Fn.REMU):
                    pass

            params_fifo.write(m, {"rob_id": arg.rob_id, "rp_dst": arg.rp_dst})
            divider.issue(m, {"divident": dividend, "divisor": divisor})

        with Transaction().body(m):
            response = divider.accept(m)
            params = params_fifo.read(m)

            result_fifo.write(
                m,
                arg={
                    "rob_id": params.rob_id,
                    "result": response.q,
                    "rp_dst": params.rp_dst,
                },
            )

        return m
