from typing import Optional
from amaranth import *
from coreblocks.transactions import *
from coreblocks.transactions.lib import *
from coreblocks.utils import *
from coreblocks.params import *
from coreblocks.utils.fifo import *
from coreblocks.scheduler.wakeup_select import *
from coreblocks.fu.vector_unit.utils import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.utils._typing import ValueLike

__all__ = ["VectorTranslator"]

class VectorTranslatorEEW(Elaboratable):
    """
    Not tested, may not work.
    Probably there is a need to do mapping from widening/narrowing instructions to normal
    instructions.
    As for now it uses internal instruction to narrow data, but there is ZEXT and SEXT
    """
    def __init__(self, gen_params : GenParams, v_params : VectorParameters, put_instr : Method, report_multiplicator : Method):
       self.gen_params = gen_params
       self.v_params = v_params

       self.layouts = VectorFrontendLayouts(self.gen_params, self.v_params)
       self.issue = Method(i= self.layouts.translator_in)
       self.put_instr = put_instr
       self.report_multiplicator = report_multiplicator

       self.shape_narrowing_optypes = [
           OpType.V_ARITHMETIC_NARROWING,
           OpType.V_ARITHMETIC_NARROWING_IMM,
           OpType.V_ARITHMETIC_NARROWING_SCALAR,
           ]
       self.shape_widening_optypes = [
           OpType.V_ARITHMETIC_WIDENING,
           OpType.V_ARITHMETIC_WIDENING_IMM,
           OpType.V_ARITHMETIC_WIDENING_SCALAR]


    def generate_move_instr(self, m : TModule, org_instr, if_narrow : ValueLike, reg_id : ValueLike) -> Record:
        rec = Record(self.layouts.translator_in)
        d = {
            "exec_fn" : {
                "funct3" : Funct3.OPIVI,
                "funct7" : Mux(if_narrow, Funct6._VNARROW, Funct6._VWIDEN) * 2 + 1,
                "op_type" : OpType.V_CONTROL,
                },
            "vtype" : org_instr.vtype,
            "rp_s1" : {
                "id": reg_id,
                "type" : RegisterType.V,
                },
            "rp_dst" : {
                "id": reg_id,
                "type" : RegisterType.V,
                }
        }
        m.d.comb += assign(rec, d)
        return rec

    def eleborate(self, platform):
        m = TModule()

        reg1 = Record(self.layouts.translator_in)
        reg2 = Record(self.layouts.translator_in)
        reg_now = Record(self.layouts.translator_in)
        counter = Signal(2)
        multiplicator = Signal(2)

        with Transaction(name="trans_put_instr_buff_1").body(m, request = counter == 1):
            m.d.sync += counter.eq(0)
            self.put_instr(m, reg1)

        with Transaction(name="trans_put_instr_buff_2").body(m, request = counter == 2):
            m.d.sync += counter.eq(1)
            self.put_instr(m, reg2)

        @def_method(m, self.issue, counter == 0)
        def _(arg):
            instr1_narrowing = Signal()
            instr1_reg = Signal(self.gen_params.phys_regs_bits)
            instr1_generated = self.generate_move_instr(m, arg, instr1_narrowing, instr1_reg)
            instr2_narrowing = Signal()
            instr2_reg = Signal(self.gen_params.phys_regs_bits)
            instr2_generated =  self.generate_move_instr(m, arg, instr2_narrowing, instr2_reg)
            is_narrowing = Cat(arg.exec_fn.op_type == op for op in self.shape_narrowing_optypes).any()
            is_widening = Cat(arg.exec_fn.op_type == op for op in self.shape_widening_optypes).any()
            with m.If(is_narrowing):
                with m.If(Cat([arg.exec_fn.funct3 == funct for funct in [Funct3.OPIVV, Funct3.OPMVV, Funct3.OPFVV]]).any()):
                    m.d.comb += [
                            instr1_narrowing.eq(0),
                            instr1_reg.eq(arg.rp_s1.id),
                            instr2_narrowing.eq(1),
                            instr2_reg.eq(arg.rp_dst.id),
                            reg_now.re(instr1_generated),
                            multiplicator.eq(3),
                            ]
                    m.d.sync += reg2.eq(arg)
                    m.d.sync += reg1.eq(instr2_generated)
                    m.d.sync += counter.eq(2)
                with m.Else():
                    m.d.comb += [
                            reg_now.re(arg),
                            multiplicator.eq(2),
                            instr2_narrowing.eq(1),
                            instr2_reg.eq(arg.rp_dst.id),]
                    m.d.sync += reg1.eq(instr2_generated)
                    m.d.sync += counter.eq(1)
            with m.Elif(is_widening):
                m.d.comb += [reg_now.re(instr1_generated),
                             multiplicator.eq(3),
                             instr1_narrowing.eq(0),
                             instr1_reg.eq(arg.rp_s1.id),
                             instr2_narrowing.eq(0),
                             instr2_reg.eq(arg.rp_s2.id),
                             ]
                m.d.sync += reg2.eq(instr2_generated)
                m.d.sync += reg1.eq(arg)
                m.d.sync += counter.eq(2)
            with m.Else():
                m.d.comb += reg_now.re(arg)
                m.d.comb += multiplicator.eq(1)
            self.put_instr(m, reg_now)
            self.report_multiplicator(m, multiplicator=multiplicator)

        return m


class VectorTranslateLMUL(Elaboratable):
    pass

class VectorTranslator(Elaboratable):
    def __init__(self, gen_params : GenParams, v_params : VectorParameters):
       self.gen_params = gen_params
       self.v_params = v_params

       self.layouts = VectorFrontendLayouts(self.gen_params, self.v_params)
       self.issue = Method(i= self.layouts.translator_in)
       self.get_instr_list = [Method(o = self.layouts.translator_out) for _ in range(self.v_params.max_lmul)]


    def elaborate(self, platform) -> TModule:
        m = TModule()

        pipe = RegisterPipe(self.layouts.translator_out, self.v_params.max_lmul)
        m.submodules.pipe = pipe

        for i in range(self.v_params.max_lmul):
            self.get_instr_list[i].proxy(m, pipe.read_list[i])

        @def_method(m, self.issue)
        def _(arg):
            pass


        return m
