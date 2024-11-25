from amaranth.lib import enum


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
