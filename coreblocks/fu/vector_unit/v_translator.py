from amaranth import *
from coreblocks.transactions import *
from coreblocks.transactions.lib import *
from coreblocks.utils import *
from coreblocks.params import *
from coreblocks.utils.fifo import *
from coreblocks.scheduler.wakeup_select import *
from coreblocks.fu.vector_unit.v_layouts import *

__all__ = ["VectorTranslator"]


class VectorTranslateLMUL(Elaboratable):
    """Transforms instructions with LMUL>1 to a sequence of LMUL=1 instructions

    LMUL>8 instructions operate on a set of registers at once, so at the beginning
    we can split such instructions into set of instructions working independently
    (but in the long run it doesn't work see: vrgather).

    Generated instructions are stored in ShiftRegister and then sent to the next
    pipeline stage one by one.

    Attributes
    ----------
    issue : Method
        Method used to pass an instruction to process.
    """

    def __init__(self, gen_params: GenParams, put_instr: Method):
        """
        Parameters
        ----------
        gen_params : GenParams
            Core configuration
        put_instr : Method
            The method used to pass the instruction to the next processing stage.
        """
        self.gen_params = gen_params

        self.layouts = VectorFrontendLayouts(self.gen_params)
        self.issue = Method(i=self.layouts.translator_inner, o=self.layouts.translator_report_multiplier)
        self.put_instr = put_instr

        self.max_lmul = 8

    def generate_instr(self, m: TModule, org_instr, mask: int, end_bits: int):
        rec = Record(self.layouts.translator_inner)
        m.d.comb += assign(rec, org_instr)
        m.d.comb += rec.vtype.lmul.eq(LMUL.m1)
        m.d.comb += rec.rp_s1.id.eq((org_instr.rp_s1.id & mask) | end_bits)
        m.d.comb += rec.rp_s2.id.eq((org_instr.rp_s2.id & mask) | end_bits)
        m.d.comb += rec.rp_dst.id.eq((org_instr.rp_dst.id & mask) | end_bits)
        return rec

    def elaborate(self, platform):
        m = TModule()

        shift_reg = ShiftRegister(self.layouts.translator_inner, self.max_lmul, self.put_instr, first_transparent=True)
        m.submodules.shift_reg = shift_reg

        @def_method(m, self.issue)
        def _(arg):
            mb_writes = [MethodBrancherIn(m, shift_reg.write_list[i]) for i in range(self.max_lmul)]
            mult = Signal(bits_for(self.max_lmul))
            with m.Switch(arg.vtype.lmul):
                with m.Case(LMUL.m2):
                    mb_writes[0](self.generate_instr(m, arg, 0x1E, 0))
                    mb_writes[1](self.generate_instr(m, arg, 0x1E, 1))
                    m.d.comb += mult.eq(2)
                with m.Case(LMUL.m4):
                    mb_writes[0](self.generate_instr(m, arg, 0x1C, 0))
                    mb_writes[1](self.generate_instr(m, arg, 0x1C, 1))
                    mb_writes[2](self.generate_instr(m, arg, 0x1C, 2))
                    mb_writes[3](self.generate_instr(m, arg, 0x1C, 3))
                    m.d.comb += mult.eq(4)
                with m.Case(LMUL.m8):
                    mb_writes[0](self.generate_instr(m, arg, 0x18, 0))
                    mb_writes[1](self.generate_instr(m, arg, 0x18, 1))
                    mb_writes[2](self.generate_instr(m, arg, 0x18, 2))
                    mb_writes[3](self.generate_instr(m, arg, 0x18, 3))
                    mb_writes[4](self.generate_instr(m, arg, 0x18, 4))
                    mb_writes[5](self.generate_instr(m, arg, 0x18, 5))
                    mb_writes[6](self.generate_instr(m, arg, 0x18, 6))
                    mb_writes[7](self.generate_instr(m, arg, 0x18, 7))
                    m.d.comb += mult.eq(8)
                with m.Case():
                    mb_writes[0](arg)
                    m.d.comb += mult.eq(1)
            return {"mult": mult, "rob_id": arg.rob_id}

        return m


class VectorTranslateRS3(Elaboratable):
    """Transformation that adds rp_s3 and rp_v0 fields.

    In the backend, we need to know the address of the v0 register (for the mask)
    and original `rp_dst` register (for third operand in some instructions),
    but by default there are no such fields in layout from scalar `Scheduler`.
    This module prepares appropriate fields so that they can be used in next
    pipeline stages.

    Attributes
    ----------
    issue : Method
        Send an instruction to transform.
    """

    def __init__(self, gen_params: GenParams, put_instr: Method):
        """
        Parameters
        ----------
        gen_params : GenParams
            Core configuration
        put_instr : Method
            The method used to pass the instruction to the next processing stage.
        """
        self.gen_params = gen_params

        self.layouts = VectorFrontendLayouts(self.gen_params)
        self.issue = Method(i=self.layouts.translator_inner)
        self.put_instr = put_instr

    def elaborate(self, platform) -> TModule:
        m = TModule()

        @def_method(m, self.issue)
        def _(arg):
            rec = Record(self.layouts.translator_out)
            m.d.top_comb += assign(rec, arg)
            m.d.top_comb += rec.rp_s3.eq(arg.rp_dst)
            m.d.top_comb += rec.rp_v0.id.eq(0)
            # TODO add support for stores (rp_dst set to non valid - type X)
            self.put_instr(m, rec)

        return m


class VectorTranslateRewirteImm(Elaboratable):
    """Compact imm and s1_val

    After processing `vset{i}vl{i}` there is no need to pass
    both `imm` and `s1_val`. We will use either one or the other,
    but not both. So, to reduce the number of bits used, we can compact
    these fields and pass `imm` in `s1_val`.

    Attributes
    ----------
    issue : Method
        Send instruction to process as a request and receive processed
        output in response.
    """

    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params

        self.layouts = VectorFrontendLayouts(self.gen_params)
        self.issue = Method(i=self.layouts.translator_in, o=self.layouts.translator_inner)

    def elaborate(self, platform) -> TModule:
        m = TModule()

        @def_method(m, self.issue)
        def _(arg):
            rec = Record(self.layouts.translator_inner)
            m.d.comb += assign(rec, arg, fields=AssignType.COMMON)
            with m.If((arg.exec_fn.funct3 == Funct3.OPIVI) & ((arg.exec_fn.op_type != OpType.V_LOAD) & (arg.exec_fn.op_type != OpType.V_STORE))):
                m.d.comb += rec.s1_val.eq(arg.imm)
                m.d.comb += rec.rp_s1.type.eq(RegisterType.X)
            return rec

        return m


class VectorTranslator(Elaboratable):
    """Container holding variate vector instruction transformations

    Each instruction sent to this module is transformed by:
    - VectorTranslateRewirteImm
    - VectorTranslateLMUL
    - VectorTranslateRS3
    and then sent to the next pipeline stage. Number of instructions generated
    is sent to retirement using the `retire_mult` method.

    Attributes
    ----------
    issue : Method
        Send an instruction to transform.
    """

    def __init__(self, gen_params: GenParams, put_instr: Method, retire_mult: Method):
        """
        Parameters
        ----------
        gen_params : GenParams
            Core configuration
        put_instr : Method
            The method used to pass the instruction to the next processing stage.
        retire_mult : Method
            The method used to report the number of internal instructions generated
            from a programme instruction.
        """
        self.gen_params = gen_params
        self.put_instr = put_instr
        self.retire_mult = retire_mult

        self.layouts = VectorFrontendLayouts(self.gen_params)
        self.issue = Method(i=self.layouts.translator_in)

    def elaborate(self, platform) -> TModule:
        m = TModule()

        m.submodules.transl_rp3 = transl_rp3 = VectorTranslateRS3(self.gen_params, self.put_instr)
        m.submodules.transl_lmul = transl_lmul = VectorTranslateLMUL(self.gen_params, transl_rp3.issue)
        m.submodules.transl_rewrite_imm = transl_rewrite_imm = VectorTranslateRewirteImm(self.gen_params)

        @def_method(m, self.issue)
        def _(arg):
            rewrited_imm = transl_rewrite_imm.issue(m, arg)
            mult = transl_lmul.issue(m, rewrited_imm)
            self.retire_mult(m, mult)

        return m
