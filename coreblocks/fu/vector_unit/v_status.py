from typing import Optional
from amaranth import *
from coreblocks.transactions import *
from coreblocks.transactions.lib import *
from coreblocks.utils import *
from coreblocks.params import *
from coreblocks.fu.vector_unit.v_layouts import *

__all__ = ["VectorStatusUnit"]


def get_vlmax(m: ModuleLike, sew: Value, lmul: Value, gen_params: GenParams) -> Signal:
    """Generates circuit to calculate VLMAX

    This function generates a circuit that computes in
    combinational domain, a VLMAX based on the `sew` and
    `lmul` signals, taking into account the `vlen` configured in
    `v_params`.

    Parameters
    ----------
    m : ModuleLike
        Module to connect the generated circuit to.
    sew : Value
        SEW for which VLMAX should is to be calculated.
    lmul : Value
        LMUL for which VLMAX should is to be calculated.
    gen_params : GenParams
        Configuration of the core.
    v_params : VectorParameters
        Configuration of the vector extension.

    Returns
    -------
    vlmax : Signal
        Signal containing the calculated VLMAX.
    """
    sig = Signal(gen_params.isa.xlen)
    with m.Switch((sew << len(lmul)) | lmul):
        for s in SEW:
            for lm in LMUL:
                bits = (s << log2_int(len(LMUL), False)) | lm
                with m.Case(bits):
                    val = int(gen_params.v_params.vlen // eew_to_bits(s) * lmul_to_float(lm))
                    m.d.comb += sig.eq(val)
    return sig


class VectorStatusUnit(Elaboratable):
    """Module to process vector CSR values

    This module holds vector CSR registers values:
    - vtype
    - vstart
    - vl
    Each vector instruction passed to the vector unit, is associated with a copy of these registers,
    with values from the moment of it is processing. This guarantees
    that any instruction executed out-of-order in vector unit, will see
    the csr registers as they were defined in programme order.

    This unit is also a sink for `vset{i}vl{i}` instructions. These
    update the apropriate registers and are immediately retired.
    If the requested parameters aren't valid, `vill` is set. Current checks:
    - SEW < ELEN

    This unit is responsible for resetting vstart to 0 after each instruction.

    Attributes
    ----------
    issue : Method(one_caller = True)
        Method that has only one caller, used to pass new instructions to be processed.
        Layout: `VectorFrontendLayouts.status_in`
    get_vill : Method
        Nonexclusive method used to get the current value of `vill`.
        Layout: `VectorFrontendLayouts.get_vill`
    get_vstart : Method
        Nonexclusive method used to get the current value of `vstart`.
        Layout: `VectorFrontendLayouts.get_vstart`
    clear : Method
        Clear the internal state.
    """

    def __init__(self, gen_params: GenParams, put_instr: Method, retire: Method):
        """
        Parameters
        ----------
        gen_params : GenParams
            Core configuration.
        put_instr : Method
            Method used to pass vector instructions that operate on data to the next pipeline stage.
            Layout: VectorFrontendLayouts.status_out
        retire : Method
            Method used to inform about the retirement of vset{i}vl{i} instructions.
            Layout: FuncUnitLayouts.accept
        """
        self.gen_params = gen_params
        self.v_params = self.gen_params.v_params
        self.retire = retire
        self.put_instr = put_instr

        self.layouts = VectorFrontendLayouts(self.gen_params)
        self.get_vill = Method(o=self.layouts.get_vill, nonexclusive=True)
        self.get_vstart = Method(o=self.layouts.get_vstart, nonexclusive=True)
        self.clear = Method()
        self.issue = Method(i=self.layouts.status_in)

        self.vtype = Signal(self.gen_params.isa.xlen, reset=1 << 31)
        self.vstart = Signal(self.v_params.vstart_bits)
        self.vl = Signal(self.gen_params.isa.xlen)

    def extract_vill(self) -> Value:
        return self.vtype[31]

    def extract_vma(self) -> Value:
        return self.vtype[7]

    def extract_vta(self) -> Value:
        return self.vtype[6]

    def extract_vlmul(self, val: Optional[Value] = None) -> Value:
        if val is not None:
            return val[0:3]
        return self.vtype[0:3]

    def extract_vsew(self, val: Optional[Value] = None) -> Value:
        if val is not None:
            return val[3:6]
        return self.vtype[3:6]

    def process_vsetvl(self, m, instr):
        new_vtype = Signal(8)
        avl = Signal().like(self.vl)
        vlmax = Signal().like(self.vl)
        m.d.comb += vlmax.eq(get_vlmax(m, new_vtype[3:6], new_vtype[:3], self.gen_params))
        m.d.comb += avl.eq(vlmax)
        ill = Signal()
        valid_rs1 = Signal()
        with m.Switch(instr.imm2[-2:]):
            with m.Case(0, 1):
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
            m.d.sync += self.vtype.eq(1 << 31)
        with m.Else():
            m.d.sync += self.vtype.eq(new_vtype)

        with m.If(valid_rs1 & instr.rp_s1_reg.bool()):
            m.d.comb += avl.eq(instr.s1_val)

        with m.If(instr.rp_dst.id.bool() | instr.rp_s1_reg.bool() | (instr.imm2[-2:] == 3)):
            m.d.sync += self.vl.eq(avl)

        self.retire(m, rob_id=instr.rob_id, exception=0, result=avl, rp_dst=instr.rp_dst)

    def process_normal_instr(self, m: TModule, instr):
        output = Record(self.layouts.status_out)
        m.d.top_comb += assign(output, instr, fields=AssignType.COMMON)
        m.d.top_comb += [
            output.vtype.sew.eq(self.extract_vsew()),
            output.vtype.lmul.eq(self.extract_vlmul()),
            output.vtype.ma.eq(self.extract_vma()),
            output.vtype.ta.eq(self.extract_vta()),
            output.vtype.vl.eq(self.vl),
        ]
        self.put_instr(m, output)

    def elaborate(self, platform):
        m = TModule()

        # TODO Optimisation: Use Funct7+rs2 istead of imm2

        @def_method(m, self.issue)
        def _(arg):
            m.d.sync += self.vstart.eq(0)
            with condition(m, nonblocking=False) as branch:
                with branch(arg.exec_fn.op_type == OpType.V_CONTROL):
                    self.process_vsetvl(m, arg)
                with branch(arg.exec_fn.op_type != OpType.V_CONTROL):
                    self.process_normal_instr(m, arg)

        @def_method(m, self.clear)
        def _():
            m.d.sync += self.vstart.eq(0)
            m.d.sync += self.vl.eq(0)
            m.d.sync += self.vtype.eq(1 << 31)

        @def_method(m, self.get_vill)
        def _():
            return {"vill": self.extract_vill()}

        @def_method(m, self.get_vstart)
        def _():
            return {"vstart": self.vstart}

        return m
