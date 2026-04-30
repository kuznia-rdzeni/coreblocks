from dataclasses import dataclass
from amaranth import *
from transactron import TModule, Method, def_method


@dataclass(frozen=True)
class QSFTable:
    intervals: list[int]
    bounds: list[list[int]]
    digits: list[tuple[int, int]]


class QSFParams:
    """Quotient selection function parameters

    Parameters
    ----------
    residual_width: int
        Number of bits of residual used in QSF
    divisor_width: int
        Number of bits of divisor used in QSF
    q_bits: int
        Number of bits of quotient (log2(Radix))
    qsf_table: QSFTable
        Table for QSF
    """

    def __init__(
        self,
        *,
        residual_width: int,
        divisor_width: int,
        q_bits: int,
        qsf_table: QSFTable,
    ):
        self.residual_width = residual_width
        self.divisor_width = divisor_width
        self.q_bits = q_bits
        self.qsf_table = qsf_table


class QSFMethodLayout:
    """Quotient selection function module layouts for methods

    Parameters
    ----------
    qsf_params: QSFParams
        Parameters of QSF
    """

    def __init__(self, *, qsf_params: QSFParams):
        """
        residual - bits of residual
        divisor - bits of divisor
        q - one digit of quotient
        """
        self.qsf_in_layout = [
            ("residual", signed(qsf_params.residual_width)),
            ("divisor", qsf_params.divisor_width),
        ]
        self.qsf_out_layout = [("q", qsf_params.q_bits), ("sign", 1)]


class QSFModule(Elaboratable):
    """Module for quotient selection function
    This module returns one quotient digit, based on bits residual and divisor.
    The exact implementations depends on radix and set of digits.

    Parameters
    ----------
    qsf_params: QSFParams
        Params for QSF
    intervals: list[int]
        List of intervals for QSF
    bounds: list[list[int]]
        List of bounds for each intervals
    digits: list[tuple[int,int]]
        Set of possible values of our quotients


    Attributes
    ----------
    qsf_request: Method
        Transactional method for initiating quotient selection.
        Takes 'qsf_in_layout' as argument
        Returns result as 'qsf_out_layout'
    """

    def __init__(self, *, qsf_params: QSFParams):

        self.qsf_params = qsf_params
        self.method_layouts = QSFMethodLayout(qsf_params=self.qsf_params)
        self.intervals = qsf_params.qsf_table.intervals
        self.bounds = qsf_params.qsf_table.bounds
        self.digits = qsf_params.qsf_table.digits
        self.qsf_request = Method(
            i=self.method_layouts.qsf_in_layout,
            o=self.method_layouts.qsf_out_layout,
        )

    def elaborate(self, platform):
        m = TModule()

        @def_method(m, self.qsf_request)
        def _(residual, divisor):
            q = Signal(self.qsf_params.q_bits)
            sign = Signal()
            for i in range(0, len(self.intervals)):
                with m.If(divisor == Const(self.intervals[i])):
                    with m.If(residual < Const(self.bounds[i][0])):
                        m.d.av_comb += q.eq(Const(self.digits[0][1]))
                        m.d.av_comb += sign.eq(Const(self.digits[0][0]))
                    for j in range(1, len(self.bounds[i])):
                        with m.Elif(residual < Const(self.bounds[i][j])):
                            m.d.av_comb += q.eq(Const(self.digits[j][1]))
                            m.d.av_comb += sign.eq(Const(self.digits[j][0]))
                    with m.Else():
                        m.d.av_comb += q.eq(Const(self.digits[len(self.bounds[i])][1]))
                        m.d.av_comb += sign.eq(Const(self.digits[len(self.bounds[i])][0]))
            return {"q": q, "sign": sign}

        return m
