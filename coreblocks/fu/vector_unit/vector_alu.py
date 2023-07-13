from amaranth import *
from typing import Callable
from enum import IntFlag, auto
from coreblocks.transactions import *
from coreblocks.transactions.lib import *
from coreblocks.utils import *
from coreblocks.params import *
from coreblocks.utils.fifo import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.fu.vector_unit.utils import *
from coreblocks.fu.vector_unit.flexible_functions import *
from coreblocks.fu.fu_decoder import DecoderManager

__all__ = ["VectorBasicFlexibleAlu"]

class VectorAluFn(DecoderManager):
    class Fn(IntFlag):
        SUB = auto()  # Subtraction
        ADD = auto()  # Addition
        SRA = auto()  # Arithmetic right shift
        SLL = auto()  # Logic left shift
        SRL = auto()  # Logic right shift
        SLE = auto()  # Set if less or equal than (signed)
        SLEU = auto()  # Set if less or equal than (unsigned)
        SLT = auto()  # Set if less than (signed)
        SLTU = auto()  # Set if less than (unsigned)
        SEQ = auto()  # Set if equal
        XOR = auto()  # Bitwise xor
        OR = auto()  # Bitwise or
        AND = auto()  # Bitwise and
        MIN = auto()
        MINU = auto()
        MAX = auto()
        MAXU = auto()

    def get_instructions(self) -> Sequence[tuple]:
        funct6_list = [
           (self.Fn.SUB, OpType.V_ARITHMETIC, Funct6.VSUB),
           (self.Fn.ADD, OpType.V_ARITHMETIC, Funct6.VADD),
           (self.Fn.SRA, OpType.V_ARITHMETIC, Funct6.VSRA),
           (self.Fn.SLL, OpType.V_ARITHMETIC, Funct6.VSLL),
           (self.Fn.SRL, OpType.V_ARITHMETIC, Funct6.VSRL),
           (self.Fn.SLE, OpType.V_ARITHMETIC, Funct6.VMSLE),
           (self.Fn.SLEU, OpType.V_ARITHMETIC, Funct6.VMSLEU),
           (self.Fn.SLT, OpType.V_ARITHMETIC, Funct6.VMSLT),
           (self.Fn.SLTU, OpType.V_ARITHMETIC, Funct6.VMSLTU),
           (self.Fn.SEQ, OpType.V_ARITHMETIC, Funct6.VMSEQ),
           (self.Fn.XOR, OpType.V_ARITHMETIC, Funct6.VXOR),
           (self.Fn.OR, OpType.V_ARITHMETIC, Funct6.VOR),
           (self.Fn.AND, OpType.V_ARITHMETIC, Funct6.VAND),
           (self.Fn.MIN, OpType.V_ARITHMETIC, Funct6.VMIN),
           (self.Fn.MINU, OpType.V_ARITHMETIC, Funct6.VMINU),
           (self.Fn.MAX, OpType.V_ARITHMETIC, Funct6.VMAX),
           (self.Fn.MAXU, OpType.V_ARITHMETIC, Funct6.VMAXU),
                ]
        return [(fn, op, None, funct6 * 2) for fn, op, funct6 in funct6_list]

class FlexibleAluExecutor(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params
        self.v_params = self.gen_params.v_params

        self.fn = VectorAluFn()

        self.in1 = Signal(self.v_params.elen)
        self.in2 = Signal(self.v_params.elen)
        self.out = Signal(self.v_params.elen)
        self.exec_fn = Record(self.gen_params.get(CommonLayouts).exec_fn)
        self.eew = Signal(EEW)

    def connect_flexible_elementwise_function(self, m : TModule, flex_m : FlexibleElementwiseFunction):
        m.d.top_comb += flex_m.eew.eq(self.eew)
        m.d.top_comb += flex_m.in1.eq(self.in1)
        m.d.top_comb += flex_m.in2.eq(self.in2)
        m.d.comb += self.out.eq(flex_m.out_data)

    def create_flexible_elementwise_function(self, m: TModule, name : str, op : Callable[[Value, Value], ValueLike]):
        flexible = FlexibleElementwiseFunction( bits_to_eew(self.v_params.elen), op)
        m.submodules[name] = flexible
        self.connect_flexible_elementwise_function(m, flexible)

    def elaborate(self, platform):
        m = TModule()

        out_width =bits_to_eew(self.v_params.elen)

        m.submodules.decoder = decoder = self.fn.get_decoder(self.gen_params)
        m.submodules.adder = adder = FlexibleAdder(out_width)

        m.d.top_comb += assign(decoder.exec_fn, self.exec_fn, fields = AssignType.ALL)
        m.d.top_comb += adder.eew.eq(self.eew)
        m.d.top_comb += adder.in1.eq(self.in1)
        m.d.top_comb += adder.in2.eq(self.in2)
        with OneHotSwitch(m, decoder.decode_fn) as OneHotCase:
            with OneHotCase(VectorAluFn.Fn.ADD):
                m.d.comb += self.out.eq(adder.out_data)
            with OneHotCase(VectorAluFn.Fn.SUB):
                m.d.comb += adder.subtract.eq(1)
                m.d.comb += self.out.eq(adder.out_data)
            with OneHotCase(VectorAluFn.Fn.SRA):   # Arithmetic right shift
                with m.Switch(self.eew):
                    for eew_iter in EEW:
                        eew_iter_bits = eew_to_bits(eew_iter)
                        if eew_to_bits(eew_iter) <= self.v_params.elen:
                            with m.Case(eew_iter):
                                # there are two lambdas to capture width by copy
                                self.create_flexible_elementwise_function(m,
                                                                          f"flexible_sra_{eew_iter_bits}", 
                                                                          (lambda width: lambda x, y: x.as_signed() >> (y[:log2_int(width)]))(eew_iter_bits)) #TODO optimise number of FlexibleElementWiseFunction's creates
            with OneHotCase(VectorAluFn.Fn.SLL):   # Logic left shift
                with m.Switch(self.eew):
                    for eew_iter in EEW:
                        eew_iter_bits = eew_to_bits(eew_iter)
                        if eew_to_bits(eew_iter) <= self.v_params.elen:
                            with m.Case(eew_iter):
                                self.create_flexible_elementwise_function(m,
                                                                          f"flexible_sll_{eew_iter_bits}",
                                                                          (lambda width: lambda x, y: x << y[:log2_int(width)])(eew_iter_bits))
            with OneHotCase(VectorAluFn.Fn.SRL):   # Logic right shift
                with m.Switch(self.eew):
                    for eew_iter in EEW:
                        eew_iter_bits = eew_to_bits(eew_iter)
                        if eew_iter_bits <= self.v_params.elen:
                            with m.Case(eew_iter):
                                self.create_flexible_elementwise_function(m,
                                                                          f"flexible_srl_{eew_iter_bits}",
                                                                          (lambda width: lambda x, y: x >> y[:log2_int(width)])(eew_iter_bits))
            with OneHotCase(VectorAluFn.Fn.SLE):   # Set if less or equal than (signed)
                self.create_flexible_elementwise_function(m, "flexible_sle", lambda x, y: Mux(x.as_signed() <= y.as_signed(), 1, 0))
            with OneHotCase(VectorAluFn.Fn.SLEU):   # Set if less or equal than (unsigned)
                self.create_flexible_elementwise_function(m, "flexible_sleu", lambda x, y: Mux(x <= y, 1, 0))
            with OneHotCase(VectorAluFn.Fn.SLT):   # Set if less than (signed)
                self.create_flexible_elementwise_function(m, "flexible_slt", lambda x, y: Mux(x.as_signed() < y.as_signed(), 1, 0))
            with OneHotCase(VectorAluFn.Fn.SLTU):   # Set if less than (unsigned)
                self.create_flexible_elementwise_function(m, "flexible_sltu", lambda x, y: Mux(x < y, 1, 0))
            with OneHotCase(VectorAluFn.Fn.SEQ):   # Set if equal
                self.create_flexible_elementwise_function(m, "flexible_seq", lambda x, y: Mux(x == y, 1, 0))
            with OneHotCase(VectorAluFn.Fn.XOR):   # Bitwise xor
                m.d.comb += self.out.eq(self.in1 ^ self.in2)
            with OneHotCase(VectorAluFn.Fn.OR):   # Bitwise or
                m.d.comb += self.out.eq(self.in1 | self.in2)
            with OneHotCase(VectorAluFn.Fn.AND):   # Bitwise and
                m.d.comb += self.out.eq(self.in1 & self.in2)
            with OneHotCase(VectorAluFn.Fn.MIN): 
                self.create_flexible_elementwise_function(m, "flexible_min", lambda x, y: Mux(x.as_signed() < y.as_signed(), x, y))
            with OneHotCase(VectorAluFn.Fn.MINU): 
                self.create_flexible_elementwise_function(m, "flexible_minu", lambda x, y: Mux(x < y, x, y))
            with OneHotCase(VectorAluFn.Fn.MAX): 
                self.create_flexible_elementwise_function(m, "flexible_max", lambda x, y: Mux(x.as_signed() > y.as_signed(), x, y))
            with OneHotCase(VectorAluFn.Fn.MAXU): 
                self.create_flexible_elementwise_function(m, "flexible_maxu", lambda x, y: Mux(x > y, x, y))


        return m

class VectorBasicFlexibleAlu(Elaboratable):
    def __init__(self, gen_params: GenParams, put_output : Method):
        self.gen_params = gen_params
        self.v_params = self.gen_params.v_params
        self.put_output = put_output

        self.layouts = VectorAluLayouts(self.gen_params)
        self.issue = Method(i = self.layouts.alu_in)

    def elaborate(self, platform) -> TModule:
        m = TModule()

        m.submodules.executor = executor = FlexibleAluExecutor(self.gen_params)

        modified_exec_fn = Record(self.gen_params.get(CommonLayouts).exec_fn)
        @def_method(m, self.issue)
        def _(s1, s2, exec_fn, eew):
            m.d.top_comb += executor.in1.eq(s1)
            m.d.top_comb += executor.in2.eq(s2)
            m.d.top_comb += executor.eew.eq(eew)
            m.d.top_comb += assign(modified_exec_fn, exec_fn, fields={"funct3", "op_type"})
            # remove vm bit
            m.d.top_comb += modified_exec_fn.funct7.eq(exec_fn.funct7[1:] << 1)
            m.d.top_comb += assign(executor.exec_fn, modified_exec_fn)

            self.put_output(m, {"dst_val" : executor.out})

        return m
