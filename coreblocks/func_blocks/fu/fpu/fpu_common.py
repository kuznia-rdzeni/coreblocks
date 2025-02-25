from amaranth.lib import enum, data


class RoundingModes(enum.Enum):
    ROUND_UP = 3
    ROUND_DOWN = 2
    ROUND_ZERO = 1
    ROUND_NEAREST_EVEN = 0
    ROUND_NEAREST_AWAY = 4


class Errors(enum.IntFlag):
    INVALID_OPERATION = enum.auto()
    DIVISION_BY_ZERO = enum.auto()
    OVERFLOW = enum.auto()
    UNDERFLOW = enum.auto()
    INEXACT = enum.auto()


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


def create_data_layout(params: FPUParams):
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
