from amaranth import *
from transactron import TModule, Method, def_method
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

    def __init__(self, *, dr_div_params: DrDivisionParams):
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
        self.div_run = Method(o=self.method_layouts.division_run_out_layout)

    def elaborate(self, platform):
        m = Tmodule()
        m.submodule.otfc = otfc = OTFCModule(otfc_params=self.otfc_params)
        m.submodule.qsf = qsf = QSFModule(qsf_params=self.qsf_params)

        additional_iterations = 2
        max_divisor = 2 ** (self.div_params.op_width) - 1

        counter = Signal(
            range(0, self.div_params.iterations + additional_iterations + 1)
        )
        residual = Signal(3 + self.div_params.op_width)
        adjusted_divisor = Signal(self.div_params.op_width + 1)

        two_p = Signal(range(0, (2 * max_divisor) + 1))
        one_p = Signal(range(0, max_divisor + 1))
        m_one_p = Signal(range(-max_divisor, 1))
        m_two_p = Signal(range(-2 * max_divisor, 1))
