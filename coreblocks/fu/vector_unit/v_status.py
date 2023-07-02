from typing import Optional
from amaranth import *
from coreblocks.transactions import *
from coreblocks.transactions.lib import *
from coreblocks.utils import *
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
        self.dependency_manager = self.gen_params.get(DependencyManager)
        self.report = self.dependency_manager.get_dependency(ExceptionReportKey())
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

    def extract_vlmul(self, val : Optional[Value] = None) -> Value:
        if val is not None:
            return val[0:3]
        return self.vtype[0:3]

    def extract_vsew(self, val : Optional[Value] = None) -> Value:
        if val is not None:
            return val[3:6]
        return self.vtype[3:6]

    def process_vsetvl(self, m, instr):
        new_vtype = Signal(8)
        avl = Signal().like(self.vl)
        ill = Signal()
        valid_rs1 = Signal()
        m.d.top_comb = avl.eq(get_vlmax(m, self.extract_vsew(new_vtype), self.extract_vlmul(new_vtype), self.gen_params, self.v_params))
        with m.Switch(instr.imm2[-2:]):
            with m.Case(0,1):
                m.d.comb += new_vtype.eq(instr.imm2[:8])
                m.d.comb += valid_rs1.eq(1)
            with m.Case(2):
                m.d.comb += new_vtype.eq(instr.s2_val[:8])
                m.d.comb += valid_rs1.eq(1)
            with m.Case(3):
                m.d.comb += new_vtype.eq(instr.imm2[:8])
                m.d.comb += avl.eq(instr.imm[:5])
        with m.If(self.extract_vsew(new_vtype) > bits_to_eew(self.v_params.elen)):
            m.d.comb += ill.eq(1)

        with m.If(ill):
            m.d.sync += self.vtype.eq(1<<31)
        with m.Else():
            m.d.sync += self.vtype.eq(new_vtype)

        with m.If(valid_rs1 & instr.rp_s1.id.bool()):
            m.d.comb += avl.eq(instr.s1_val)

        with m.If(instr.rp_dst.id.bool() | instr.rp_s1.id.bool()):
                m.d.sync += self.vl.eq(avl)

        self.retire(m, rob_id = instr.rob_id, exception = 0, result = avl, rp_dst = instr.rp_dst)

    def process_normal_instr(self, m : TModule, instr):
        output = Record(self.layouts.status_out)
        m.d.top_comb += assign(output, instr, fields=AssignType.COMMON)
        m.d.top_comb += [
                output.vtype.sew.eq(self.extract_vsew()),
                output.vtype.lmul.eq(self.extract_vlmul()),
                output.vtype.ma.eq(self.extract_vma()),
                output.vtype.ta.eq(self.extract_vta()),
                ]
        self.put_instr(m, output)

    def elaborate(self, platform):
        m = TModule()

        fifo = BasicFifo(self.layouts.status_in, 2)
        m.submodules.fifo = fifo

        self.issue.proxy(m, fifo.write)

        status_handler = Transaction(name = "status_handler")

        with status_handler.body(m):
            instr = fifo.read(m)
            with condition(m, nonblocking = False) as branch:
                with branch(fifo.head.exec_fn.op_type == OpType.V_CONTROL):
                    self.process_vsetvl(m, instr)
                with branch():
                    self.process_normal_instr(m, instr)
            m.d.sync += self.vstart.eq(0)
            with condition(m) as branch:
                with branch(self.vstart != 0):
                    self.report(m, rob_id = instr.rob_id, cause = ExceptionCause.ILLEGAL_INSTRUCTION)
                    self.retire(m, rob_id = instr.rob_id, exception = 1)

        return m
