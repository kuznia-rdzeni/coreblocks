from amaranth.lib import enum


class RoundingModes(enum.Enum, shape=3):
    ROUND_UP = 3
    ROUND_DOWN = 2
    ROUND_ZERO = 1
    ROUND_NEAREST_EVEN = 0
    ROUND_NEAREST_AWAY = 4


class FPUParams:
    """FPU parameters

    Parameters
    ----------
    sig_width: int
        Width of significand
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


class FPURoundingParams:
    """FPU rounding module signature

    Parameters
    ----------
    fpu_params: FPUParams
        FPU parameters
    is_rounded:bool
        This flags indicates that the input number was already rounded.
        This creates simpler version of rounding module that only performs error checking and returns correct number.
    """

    def __init__(self, fpu_params: FPUParams, *, is_rounded: bool = False):
        self.fpu_params = fpu_params
        self.is_rounded = is_rounded
