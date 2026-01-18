from amaranth.lib import enum, data


class RoundingModes(enum.Enum):
    ROUND_UP = 3
    ROUND_DOWN = 2
    ROUND_ZERO = 1
    ROUND_NEAREST_EVEN = 0
    ROUND_NEAREST_AWAY = 4


class Errors(enum.IntFlag):
    INEXACT = enum.auto()
    UNDERFLOW = enum.auto()
    OVERFLOW = enum.auto()
    DIVISION_BY_ZERO = enum.auto()
    INVALID_OPERATION = enum.auto()


class FPUClasses(enum.IntFlag, shape=10):
    NEG_INF = enum.auto()
    NEG_NORM = enum.auto()
    NEG_SUB = enum.auto()
    NEG_ZERO = enum.auto()
    POS_ZERO = enum.auto()
    POS_SUB = enum.auto()
    POS_NORM = enum.auto()
    POS_INF = enum.auto()
    SIG_NAN = enum.auto()
    QUIET_NAN = enum.auto()


class FPUParams:
    """FPU parameters

    Parameters
    ----------
    sig_width: int
        Width of significand, including implicit bit
    exp_width: int
        Width of exponent
    """

    def __init__(
        self,
        *,
        sig_width: int = 24,
        exp_width: int = 8,
    ):
        self.sig_width = sig_width
        self.exp_width = exp_width


def create_data_output_layout(params: FPUParams):
    """A function that creates a layout for FPU modules results.

    Parameters
    ----------
    fpu_params; FPUParams
        FPU parameters
    """
    return data.StructLayout(
        {
            "sign": 1,
            "sig": params.sig_width,
            "exp": params.exp_width,
            "errors": Errors,
        }
    )


def create_data_input_layout(params: FPUParams):
    """A function that creates a layout for FPU modules operands.

    Parameters
    ----------
    fpu_params; FPUParams
        FPU parameters
    """
    return data.StructLayout(
        {
            "sign": 1,
            "sig": params.sig_width,
            "exp": params.exp_width,
            "is_inf": 1,
            "is_nan": 1,
            "is_zero": 1,
        }
    )


def create_raw_float_layout(params: FPUParams):
    return data.StructLayout(
        {
            "sign": 1,
            "sig": params.sig_width,
            "exp": params.exp_width,
        }
    )


def create_output_layout(params: FPUParams):
    return data.StructLayout(
        {
            "sign": 1,
            "sig": params.sig_width,
            "exp": params.exp_width,
            "errors": Errors,
        }
    )


class FPUCommonValues:
    def __init__(self, fpu_params: FPUParams):
        self.params = fpu_params
        self.canonical_nan_sig = (2 ** (fpu_params.sig_width - 1)) | (2 ** (fpu_params.sig_width - 2))
        self.max_exp = (2**self.params.exp_width) - 1
        self.max_sig = (2**self.params.sig_width) - 1
