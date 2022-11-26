from enum import Enum

__all__ = ["MulUnitParams", "MulType"]


class MulType(Enum):
    SHIFT_MUL = 0
    SEQUENCE_MUL = 1
    RECURSIVE_MUL = 2


class MulUnitParams:
    def __init__(self, mul_type: MulType, dsp_width: int = 16):
        self.mul_type = mul_type
        if mul_type != MulType.SHIFT_MUL:
            self.width = dsp_width

    @classmethod
    def ShiftMultiplicator(cls) -> "MulUnitParams":
        """
        The cheapest multiplication unit in terms of resources, it uses Russian Peasants Algorithm
        """
        return MulUnitParams(MulType.SHIFT_MUL)

    @classmethod
    def SequanceMultiplicator(cls, dsp_width) -> "MulUnitParams":
        """
        Uses single DSP unit for multiplication, which makes balance between performance and cost

        Parameters
        ----------
        dsp_width: int
            width of numbers that will be multiplied in single clock cycle by DSP
        """
        return MulUnitParams(MulType.SEQUENCE_MUL, dsp_width)

    @classmethod
    def RecursiveMultiplicator(cls, dsp_width) -> "MulUnitParams":
        """
        Fastest way of multiplying using only one cycle, but costly in terms of resources

        Parameters
        ----------
        dsp_width: int
            width of numbers that will be multiplied in single clock cycle by DSP
        """
        return MulUnitParams(MulType.RECURSIVE_MUL, dsp_width)
