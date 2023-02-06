from enum import IntFlag, unique
from amaranth import Signal, Module, Elaboratable, Record, Mux, Cat

from coreblocks.params import (
    Funct3,
    CommonLayouts,
    GenParams,
    FuncUnitLayouts,
    OpType,
    Funct7,
    FunctionalComponentParams,
    ComponentDependencies,
)
from coreblocks.transactions import Method
from coreblocks.transactions.lib import FIFO
from coreblocks.transactions.core import def_method
from coreblocks.utils import OneHotSwitch
from coreblocks.utils.protocols import FuncUnit


class ZbsFunction(Signal):
    """
    Enum of Zbs functions.
    """

    @unique
    class Function(IntFlag):
        BCLR = 1 << 0  # Bit clear
        BEXT = 1 << 1  # Bit extract
        BINV = 1 << 2  # Bit invert
        BSET = 1 << 3  # Bit set

    def __init__(self, *args, **kwargs):
        super().__init__(ZbsFunction.Function, *args, **kwargs)


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


class Zbs(Elaboratable):
    """
    Module responsible for executing Zbs instructions.

    Attributes
    ----------
    function: ZbsFunction, in
        Function to be executed.
    in1: Signal(xlen), in
        First input.
    in2: Signal(xlen), in
        Second input.

    Args:
    ----
        gen_params: Core generation parameters.
    """

    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params

        self.xlen = gen_params.isa.xlen
        self.function = ZbsFunction()
        self.in1 = Signal(self.xlen)
        self.in2 = Signal(self.xlen)

        self.result = Signal(self.xlen)

    def elaborate(self, platform):
        m = Module()

        xlen_log = self.gen_params.isa.xlen_log

        with OneHotSwitch(m, self.function) as OneHotCase:
            with OneHotCase(ZbsFunction.Function.BCLR):
                m.d.comb += self.result.eq(self.in1 & ~(1 << self.in2[0:xlen_log]))
            with OneHotCase(ZbsFunction.Function.BEXT):
                m.d.comb += self.result.eq((self.in1 >> self.in2[0:xlen_log]) & 1)
            with OneHotCase(ZbsFunction.Function.BINV):
                m.d.comb += self.result.eq(self.in1 ^ (1 << self.in2[0:xlen_log]))
            with OneHotCase(ZbsFunction.Function.BSET):
                m.d.comb += self.result.eq(self.in1 | (1 << self.in2[0:xlen_log]))

        return m


class ZbsUnit(Elaboratable):
    """
    Module responsible for executing Zbs instructions.

    Attributes
    ----------
    issue: Method(i=FuncUnitLayouts.issue)
        Method used for requesting computation.
    accept: Method(i=FuncUnitLayouts.accept)
        Method used for getting result of requested computation.
    """

    optypes = {OpType.SINGLE_BIT_MANIPULATION}

    def __init__(self, gen_params: GenParams):
        layouts = gen_params.get(FuncUnitLayouts)

        self.gen_params = gen_params
        self.issue = Method(i=layouts.issue)
        self.accept = Method(o=layouts.accept)

    def elaborate(self, platform):
        m = Module()

        m.submodules.zbs = zbs = Zbs(self.gen_params)
        m.submodules.result_fifo = result_fifo = FIFO(self.gen_params.get(FuncUnitLayouts).accept, 2)
        m.submodules.decoder = decoder = ZbsFunctionDecoder(self.gen_params)

        @def_method(m, self.accept)
        def _(arg):
            return result_fifo.read(m)

        @def_method(m, self.issue)
        def _(arg):
            m.d.comb += decoder.exec_fn.eq(arg.exec_fn)

            m.d.comb += zbs.function.eq(decoder.zbs_function)
            m.d.comb += zbs.in1.eq(arg.s1_val)
            m.d.comb += zbs.in2.eq(Mux(arg.imm, arg.imm, arg.s2_val))

            result_fifo.write(m, arg={"rob_id": arg.rob_id, "result": zbs.result, "rp_dst": arg.rp_dst})

        return m


class ZbsComponent(FunctionalComponentParams):
    def get_module(self, gen_params: GenParams, dependencies: ComponentDependencies) -> FuncUnit:
        return ZbsUnit(gen_params)

    def get_optypes(self) -> set[OpType]:
        return ZbsUnit.optypes
