from typing import Optional
from amaranth import *
from coreblocks.transactions import *
from coreblocks.transactions.lib import *
from coreblocks.params import *
from coreblocks.fu.vector_unit.utils import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.utils.fifo import BasicFifo


class VectorStatusUnit(Elaboratable):
    def __init__(self, gen_params: GenParams, v_params: VectorParameters, retire : Method, put_instr : Method):
        self.gen_params = gen_params
        self.v_params = v_params
        self.retire = retire
        self.put_instr = put_instr

        self.layouts = VectorFrontendLayouts(self.gen_params, self.v_params)
        self.get_vill = Method(o = self.layouts.get_vill, nonexclusive=True)
        self.get_vstart = Method(o = self.layouts.get_vstart, nonexclusive = True)
        self.clear = Method()
        self.issue = Method(i = self.layouts.status_in)

        self.vtype = Signal(self.gen_params.isa.xlen, reset = 1<<31)
        self.vstart = Signal(self.v_params.vstart_bits)
        self.vl = Signal(self.gen_params.isa.xlen)

    def extract_vill(self) -> Value:
        return self.vtype[31]

    def extract_vma(self) -> Value:
        return self.vtype[7]

    def extract_vta(self) -> Value:
        return self.vtype[6]

    def extract_vlmul(self) -> Value:
        return self.vtype[0:3]

    def extract_vsew(self, val : Optional[Value] = None) -> Value:
        if val is not None:
            return val[3:6]
        return self.vtype[3:6]

    def process_vsetvl(self, m, instr):
        new_vtype = Signal(8)
        avl = Signal().like(self.vl)
        ill = Signal()
        with m.Switch(instr.imm2[-2:]):
            with m.Case(0,1):
                m.d.comb += new_vtype.eq(instr.imm2[:8])
                m.d.comb += avl.eq(instr.s1_val)
            with m.Case(2):
                m.d.comb += new_vtype.eq(instr.s2_val[:8])
                m.d.comb += avl.eq(instr.s1_val)
            with m.Case(3):
                m.d.comb += new_vtype.eq(instr.imm2[:8])
                m.d.comb += avl.eq(instr.imm[:5])
        with m.If(self.extract_vsew(new_vtype) > bits_to_eew(self.v_params.elen)):
            m.d.comb += ill.eq(1)
        #TODO VLMAX i ograniczanie i zwracanie


    def elaborate(self, platform):
        m = TModule()

        fifo = BasicFifo(self.layouts.status_in, 2)
        m.submodules.fifo = fifo

        self.issue.proxy(m, fifo.write)

        with Transaction(name = "status_handler").body(m):
            instr = fifo.read(m)
            with condition(m, nonblocking = False) as branch:
                with branch(fifo.head.exec_fn.op_type == OpType.V_CONTROL):
                    pass
                with branch():
                    pass

        return m
