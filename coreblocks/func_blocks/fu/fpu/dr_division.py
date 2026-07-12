from amaranth import *
from transactron import TModule, Method, def_method, Transaction
from transactron.utils import from_method_layout
from coreblocks.func_blocks.fu.fpu.otfc import *
from coreblocks.func_blocks.fu.fpu.qsf_tables import *
from coreblocks.func_blocks.fu.fpu.fpu_qsf import *


class DrDivParams:
    """Division by digit recurrence parameters

    Parameters
    ----------
    iterations: int
        Number of iterations of digit recurrence
    op_width: int
        width of operands
    result_width: int
        width of result
    """

    def __init__(self, *, iterations: int, op_width: int, result_width: int):
        self.iterations = iterations
        self.op_width = op_width
        self.result_width = result_width


class DrDivMethodLayout:
    """Division by digit recurrence module metohds layouts

    Parameters
    ----------
    dr_div_params: DrDivParams
        Parameters of division
    """

    def __init__(self, *, dr_div_params: DrDivParams):
        """
        d - divisor
        x - dividend
        result - result of operation
        zero_rem - flag indicating if remainder is zero
        """

        self.division_init_in_layout = [
            ("d", dr_div_params.op_width),
            ("x", dr_div_params.op_width),
        ]
        self.division_run_out_layout = [
            ("result", dr_div_params.result_width),
            ("zero_rem", 1),
        ]


class DrDivModule(Elaboratable):
    """Module for performing division by digit recurrence

    Parameters
    ----------
    div_params: DrDivParams
        Params for division

    Attributes
    ----------
    div_init: Method
        Transactional method for initiating division
        Takes 'division_init_in_layout' as argument
    div_run: Method
        Performs division operation
        Returns 'division_run_out_layout' as argument
    """

    def __init__(self, *, div_params: DrDivParams, qsf_params: QSFParams):
        self.div_params = div_params
        self.qsf_params = qsf_params
        self.otfc_params = OTFCParams(result_width=self.div_params.result_width)
        self.method_layouts = DrDivMethodLayout(dr_div_params=div_params)
        self.div_init = Method(i=self.method_layouts.division_init_in_layout)
        self.div_result = Method(o=self.method_layouts.division_run_out_layout)

    def elaborate(self, platform):
        m = TModule()
        m.submodules.otfc = otfc = OTFCModule(otfc_params=self.otfc_params)
        m.submodules.qsf = qsf = QSFModule(qsf_params=self.qsf_params)

        additional_iterations = 2
        integer_bits = 3
        counter_max = self.div_params.iterations + additional_iterations

        counter = Signal(range(0, counter_max + 1))
        residual = Signal(signed(integer_bits + self.div_params.op_width))
        divisor = Signal(1 + self.div_params.op_width)

        two_p = Signal(signed(2 + self.div_params.op_width))
        one_p = Signal(signed(2 + self.div_params.op_width))
        m_one_p = Signal(signed(2 + self.div_params.op_width))
        m_two_p = Signal(signed(2 + self.div_params.op_width))

        init_ready = Signal()
        result_ready = Signal()
        residual_negative = Signal()

        otfc_response = Signal(from_method_layout(otfc.method_layouts.otfc_result_out_layout))
        qsf_response = Signal(from_method_layout(qsf.method_layouts.qsf_out_layout))

        @def_method(m, self.div_init)
        def _(x, d):
            m.d.sync
            m.d.sync += divisor.eq(d)
            m.d.sync += residual.eq(x)
            m.d.sync += residual_negative.eq(0)
            # Divisor does not change through the entirety of the division
            # so we precompute all the possible value of q*d
            m.d.sync += two_p.eq(2 * d)
            m.d.sync += one_p.eq(d)
            m.d.sync += m_one_p.eq(-1 * d)
            m.d.sync += m_two_p.eq(-2 * d)
            m.d.sync += counter.eq(1)
            m.d.sync += result_ready.eq(0)
            m.d.sync += init_ready.eq(1)
            m.d.sync += Print("INIT: ", x, " ", d)
            m.d.sync += Print("1d: ", one_p)

        with m.If((counter < (self.div_params.iterations + additional_iterations)) & init_ready):
            m.d.sync += Print("COUNTER: ", counter, " r: ", residual, " d: ", divisor)
            new_residual = Signal(self.div_params.op_width + 1)

            with Transaction().body(m):
                m.d.sync += Print(
                    "qsf res: ",
                    residual[-7:].as_signed(),
                    " divisor: ",
                    (divisor[-5:] << 0),
                )
                resp_qsf = qsf.qsf_request(m, residual=residual[-7:].as_signed(), divisor=(divisor[-5:] << 0))
                m.d.comb += qsf_response.eq(resp_qsf)
                otfc.otfc_add_digit(m, sign=qsf_response["sign"], q=qsf_response["q"])
            m.d.sync += counter.eq(counter + 1)
            # To check if the last residual is zero we keep this
            # information in a separate flag before we compute new residual
            m.d.sync += residual_negative.eq(residual < 0)
            # The residual is extended by two integer bits for the purpose of shift by 2 (4*R[j])
            # but only one integer bit is used in recurrence
            # so we use additional signal to cut off those two bits
            m.d.sync += Print("qsf resp = ", qsf_response["q"], " sign: ", qsf_response["sign"])
            with m.Switch(qsf_response["q"]):
                with m.Case(2):
                    with m.If(qsf_response["sign"] == 1):
                        m.d.comb += new_residual.eq(residual - m_two_p)
                    with m.Else():
                        m.d.comb += new_residual.eq(residual - two_p)
                with m.Case(1):
                    with m.If(qsf_response["sign"] == 1):
                        m.d.comb += new_residual.eq(residual - m_one_p)
                    with m.Else():
                        m.d.comb += new_residual.eq(residual - one_p)
                with m.Case(0):
                    m.d.comb += new_residual.eq(residual)
            m.d.sync += Print("new residual: ", new_residual)
            m.d.sync += residual.eq(new_residual << 2)  # R[j + 1] = 4*R[j]
        with m.Elif(counter == (counter_max)):
            m.d.sync += result_ready.eq(1)
            m.d.sync += init_ready.eq(0)

        @def_method(m, self.div_result, ready=result_ready)
        def _():
            zero_rem = Signal()
            adjusted_result = Signal(self.div_params.result_width)
            m.d.comb += zero_rem.eq(~residual.any())
            with Transaction().body(m):
                resp = otfc.otfc_result(m, shift=0)
                m.d.comb += otfc_response.eq(resp)
            m.d.sync += Print("RESULT: ", otfc_response["result"])
            with m.If(residual_negative):
                m.d.comb += adjusted_result.eq((otfc_response["result"] - 1) << 2)
            with m.Else():
                m.d.comb += adjusted_result.eq(otfc_response["result"] << 2)
            return {"result": adjusted_result, "zero_rem": zero_rem}

        return m
