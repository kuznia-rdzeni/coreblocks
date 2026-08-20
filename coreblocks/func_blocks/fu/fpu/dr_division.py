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
    fractional_bits: int
        width of the fractional part of the float
    result_fractional_bits: int
        Fractional bits of the result we want to compute. The integer bits are always zero before shift
    """

    def __init__(
        self,
        *,
        iterations: int,
        fractional_bits: int,
        result_fractional_bits: int,
    ):
        self.iterations = iterations
        self.fractional_bits = fractional_bits
        self.result_fractional_bits = result_fractional_bits


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
        # This algorithm uses fp number with range [1/2;1),
        # so we only get number of fractional bits
        self.division_init_in_layout = [
            ("d", dr_div_params.fractional_bits),
            ("x", dr_div_params.fractional_bits),
        ]
        self.division_run_out_layout = [
            (
                "result",
                dr_div_params.result_fractional_bits,
            ),
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
        self.otfc_params = OTFCParams(result_width=self.div_params.result_fractional_bits)
        self.method_layouts = DrDivMethodLayout(dr_div_params=div_params)
        self.div_init = Method(i=self.method_layouts.division_init_in_layout)
        self.div_result = Method(o=self.method_layouts.division_run_out_layout)

    def elaborate(self, platform):
        m = TModule()
        m.submodules.otfc = otfc = OTFCModule(otfc_params=self.otfc_params)
        m.submodules.qsf = qsf = QSFModule(qsf_params=self.qsf_params)

        # Integer bits needed for residual computation
        integer_bits = 3
        counter_max = self.div_params.iterations

        counter = Signal(range(0, counter_max + 1))
        residual = Signal(signed(integer_bits + self.div_params.fractional_bits))
        divisor = Signal(1 + self.div_params.fractional_bits)

        two_p = Signal(signed(2 + self.div_params.fractional_bits))
        one_p = Signal(signed(2 + self.div_params.fractional_bits))
        m_one_p = Signal(signed(2 + self.div_params.fractional_bits))
        m_two_p = Signal(signed(2 + self.div_params.fractional_bits))

        residual_negative = Signal()
        residual_is_zero = Signal()
        residual_is_minus_d = Signal()
        otfc_response = Signal(from_method_layout(otfc.method_layouts.otfc_result_out_layout))
        qsf_response = Signal(from_method_layout(qsf.method_layouts.qsf_out_layout))

        with m.FSM(init="Idle"):
            with m.State("Idle"):

                @def_method(m, self.div_init)
                def _(x, d):
                    m.d.sync += divisor.eq(d)
                    m.d.sync += residual.eq(x)
                    m.d.sync += residual_negative.eq(0)
                    m.d.sync += residual_is_minus_d.eq(0)
                    # We assume that divisor is not zero
                    m.d.sync += residual_is_zero.eq(0)
                    # Divisor does not change through the entirety of the division
                    # so we precompute all the possible value of q*d
                    m.d.sync += two_p.eq(2 * d)
                    m.d.sync += one_p.eq(d)
                    m.d.sync += m_one_p.eq(-1 * d)
                    m.d.sync += m_two_p.eq(-2 * d)
                    m.d.sync += counter.eq(0)
                    m.next = "Loop"

            with m.State("Loop"):
                # The residual for the next iteration. This Signal could have the same shape
                # as residual, but those two MSB bits would be shifted out anyway.
                new_residual = Signal(self.div_params.fractional_bits + 1)

                with Transaction().always_body(m):
                    m.d.av_comb += qsf_response.eq(
                        qsf.qsf_request(
                            m,
                            residual=residual[-7:].as_signed(),
                            divisor=(divisor[-5:] << 0),
                        )
                    )
                    otfc.otfc_add_digit(m, sign=qsf_response["sign"], q=qsf_response["q"])
                m.d.sync += counter.eq(counter + 1)
                # To check if the last residual is zero we keep this
                # information in a separate flag before we compute new residual
                # This applies to the other flags as well
                m.d.sync += residual_negative.eq(residual < 0)
                m.d.sync += residual_is_zero.eq(residual == 0)
                # The residual is extended by two integer bits
                # for the purpose of shift by 2 (4*R[j])
                # but only one integer bit is used in recurrence
                # so we use additional signal to cut off those two bits
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
                m.d.sync += residual.eq(new_residual << 2)  # R[j + 1] = 4*R[j]
                next_counter = counter + 1
                with m.If(next_counter == counter_max):
                    m.next = "Result"
            with m.State("Result"):

                @def_method(m, self.div_result)
                def _():
                    zero_rem = Signal()
                    adjusted_result = Signal(self.div_params.result_fractional_bits)
                    m.d.sync += counter.eq(0)
                    m.d.av_comb += otfc_response.eq(otfc.otfc_result(m, shift=0))
                    # The initialization condition requires that we shift result left by 2.
                    # We can also do this by setting correct signal shape
                    with m.If(residual_negative):
                        m.d.av_comb += zero_rem.eq(residual_is_minus_d)
                        m.d.av_comb += adjusted_result.eq((otfc_response["result"] - 1))
                    with m.Else():
                        m.d.av_comb += zero_rem.eq(residual_is_zero)
                        m.d.av_comb += adjusted_result.eq(otfc_response["result"])
                    m.next = "Idle"
                    return {"result": adjusted_result, "zero_rem": zero_rem}

        return m
