from amaranth import *
from amaranth.lib import enum
from transactron import TModule, Method, def_method
from coreblocks.func_blocks.fu.fpu.fpu_common import FPUParams, create_data_input_layout, create_data_output_layout


class SIOperations(enum.IntFlag):
    FSGNJ_S = enum.auto()  # sign of second operand
    FSGNJN_S = enum.auto()  # opposite of sign of second operand
    FSGNJX_S = enum.auto()  # xor of both signs


class SIMethodLayout:
    """Sign injection module layouts for methods

    Parameters
    ----------
    fpu_params: FPUParams
        FPU parameters
    """

    def __init__(self, *, fpu_params: FPUParams):
        """
        op_1 - first operand
        op_2 - second operand
        operation - type of sign injection operation
        """
        self.si_in_layout = [
            ("op_1", create_data_input_layout(fpu_params)),
            ("op_2", create_data_input_layout(fpu_params)),
            ("operation", SIOperations),
        ]
        self.si_out_layout = create_data_output_layout(fpu_params)


class SIModule(Elaboratable):
    """Sign injection module
    Module responsible for performing sign injection operations.
    Only things worth noting about this module are:
    1. Sign injection do not set floating-point exception flags
    2. Sign injection do not canonicalize NaNs

    Parameters
    ----------
    fpu_params: FPUParams
        FPU rounding module parameters

    Attributes
    ----------
    si_request: Method
        Transactional method for initiating leading sign injection.
        Takes 'si_in_layout' as argument
        Returns result as 'si_out_layout'
    """

    def __init__(self, *, fpu_params: FPUParams):

        self.si_params = fpu_params
        self.method_layouts = SIMethodLayout(fpu_params=self.si_params)
        self.si_request = Method(
            i=self.method_layouts.si_in_layout,
            o=self.method_layouts.si_out_layout,
        )

    def elaborate(self, platform):
        m = TModule()

        @def_method(m, self.si_request)
        def _(op_1, op_2, operation):

            final_sign = Signal()

            with m.Switch(operation):
                with m.Case(SIOperations.FSGNJ_S):
                    m.d.av_comb += final_sign.eq(op_2.sign)
                with m.Case(SIOperations.FSGNJN_S):
                    m.d.av_comb += final_sign.eq(~op_2.sign)
                with m.Case(SIOperations.FSGNJX_S):
                    m.d.av_comb += final_sign.eq(op_2.sign ^ op_1.sign)

            return {
                "sign": final_sign,
                "sig": op_1.sig,
                "exp": op_1.exp,
                "errors": 0,
            }

        return m
