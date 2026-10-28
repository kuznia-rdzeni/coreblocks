from dataclasses import dataclass
from typing import NamedTuple
from coreblocks.func_blocks.fu.fpu.fpu_common import Errors, FPUCommonValues, FPUParams, RoundingModes
from transactron.testing import *
import softfloatpy


FPU_RM_TO_SOFTFLOAT_RM = {
    RoundingModes.ROUND_UP: softfloatpy.RoundingMode.MAX,
    RoundingModes.ROUND_DOWN: softfloatpy.RoundingMode.MIN,
    RoundingModes.ROUND_ZERO: softfloatpy.RoundingMode.MIN_MAG,
    RoundingModes.ROUND_NEAREST_EVEN: softfloatpy.RoundingMode.NEAR_EVEN,
    RoundingModes.ROUND_NEAREST_AWAY: softfloatpy.RoundingMode.NEAR_MAX_MAG,
}

SF_EXCEPTION_TO_FPU_ERRORS = {
    softfloatpy.ExceptionFlag.INEXACT: Errors.INEXACT,
    softfloatpy.ExceptionFlag.UNDERFLOW: Errors.UNDERFLOW,
    softfloatpy.ExceptionFlag.OVERFLOW: Errors.OVERFLOW,
    softfloatpy.ExceptionFlag.INFINITE: Errors.DIVISION_BY_ZERO,
    softfloatpy.ExceptionFlag.INVALID: Errors.INVALID_OPERATION,
}


@dataclass(frozen=True)
class SFFormat:
    prefix: str
    byte_width: int
    sf_cls: type

    def pack(self, word: int):
        return self.sf_cls.from_bytes(word.to_bytes(self.byte_width, "big"))

    def unpack(self, sf_val) -> int:
        return int.from_bytes(sf_val.to_bytes(), "big")


@dataclass(frozen=True)
class SFIntegerFormat(SFFormat):
    pass


@dataclass(frozen=True)
class SFFloatFormat(SFFormat):
    canonical_nan: int

    def unpack(self, sf_val) -> int:
        if sf_val.is_nan():
            return self.canonical_nan

        return super().unpack(sf_val)


SF_I64 = SFIntegerFormat("i64", 8, softfloatpy.Int64)
SF_UI64 = SFIntegerFormat("ui64", 8, softfloatpy.UInt64)
SF_F32 = SFFloatFormat(
    "f32",
    4,
    softfloatpy.Float32,
    0x7FC00000,
)


class SoftFloatReference:
    def __init__(self):
        softfloatpy.set_tininess_mode(softfloatpy.TininessMode.AFTER_ROUNDING)

    @staticmethod
    def _sf_exception_to_fpu_errors(sf_exceptions: int) -> int:
        fpu_errors = 0
        for sf_exception, fpu_error in SF_EXCEPTION_TO_FPU_ERRORS.items():
            if sf_exceptions & sf_exception != 0:
                fpu_errors |= int(fpu_error)

        return fpu_errors

    @staticmethod
    def _execute_and_collect(rm: RoundingModes, fmt: SFFormat, f) -> tuple[int, int]:
        softfloatpy.set_rounding_mode(FPU_RM_TO_SOFTFLOAT_RM[rm])
        softfloatpy.set_exception_flags(0)

        sf_result = f()
        sf_exceptions = softfloatpy.get_exception_flags()

        result_raw = fmt.unpack(sf_result)
        exceptions_raw = SoftFloatReference._sf_exception_to_fpu_errors(sf_exceptions)
        return (result_raw, exceptions_raw)

    def op(self, op_name: str, fmt: SFFloatFormat, a: int, b: int, rm: RoundingModes) -> tuple[int, int]:
        sf_op = getattr(softfloatpy, f"{fmt.prefix}_{op_name}")
        sf_a = fmt.pack(a)
        sf_b = fmt.pack(b)
        return self._execute_and_collect(rm, fmt, lambda: sf_op(sf_a, sf_b))

    def mul(self, fmt: SFFloatFormat, a: int, b: int, rm: RoundingModes) -> tuple[int, int]:
        return self.op("mul", fmt, a, b, rm)

    def add(self, fmt: SFFloatFormat, a: int, b: int, rm: RoundingModes) -> tuple[int, int]:
        return self.op("add", fmt, a, b, rm)

    def sub(self, fmt: SFFloatFormat, a: int, b: int, rm: RoundingModes) -> tuple[int, int]:
        return self.op("sub", fmt, a, b, rm)

    def convert(
        self, sf_fmt_input: SFFormat, sf_fmt_output: SFFormat, input: int, rm: RoundingModes, exact: bool = True
    ) -> tuple[int, int]:
        to_float = isinstance(sf_fmt_output, SFFloatFormat)
        # Conversion between integer types is not supported
        assert to_float or isinstance(sf_fmt_input, SFFloatFormat)

        sf_convert = getattr(softfloatpy, f"{sf_fmt_input.prefix}_to_{sf_fmt_output.prefix}")
        sf_x = sf_fmt_input.pack(input)

        if to_float:
            return self._execute_and_collect(rm, sf_fmt_output, lambda: sf_convert(sf_x))
        else:
            return self._execute_and_collect(
                rm, sf_fmt_output, lambda: sf_convert(sf_x, FPU_RM_TO_SOFTFLOAT_RM[rm], exact)
            )


class FPUTester:
    def __init__(self, params: FPUParams):
        self.params = params
        self.converter = FloatConverter(params)

    async def run_test_set(self, cases, result, common_input, sim: TestbenchContext, request_adapter: TestbenchIO):
        assert len(cases) == len(result)
        for num, case in enumerate(cases):
            input_dict = {}
            for key, value in common_input.items():
                input_dict[key] = value

            input_dict["op_1"] = self.converter.to_input_data(case[0])
            input_dict["op_2"] = self.converter.to_input_data(case[1])
            resp = await request_adapter.call(sim, input_dict)

            (result_data, result_errors) = (result[num][0], result[num][1])
            expected = self.converter.to_output_data(result_data, result_errors)
            assert resp == expected


class FloatConverter:
    class FloatData(NamedTuple):
        sign: int
        exp: int
        sig: int
        sig_with_implicit_one: int

    def __init__(self, params: FPUParams):
        self.params = params
        # Width of the entire floating point number.
        # 1 is subtracted from sig_width because in memory significand is one bit
        # shorter than specified. This bit is encoded by exponent.
        sign_width = 1
        self.all_width = self.params.sig_width - 1 + self.params.exp_width + sign_width
        self.sig_width = self.params.sig_width - 1
        self.exp_mask = (2**self.params.exp_width) - 1
        self.sig_mask = (2 ** (self.params.sig_width - 1)) - 1
        self.implicit_one = 1 << (self.params.sig_width - 1)
        self.cv = FPUCommonValues(self.params)

    def _decode_float(self, raw_float: int | str) -> FloatData:
        raw_float = int(raw_float, 16) if isinstance(raw_float, str) else raw_float
        sign = (raw_float >> (self.all_width - 1)) & 0x1
        exp = (raw_float >> self.sig_width) & self.exp_mask
        sig = raw_float & self.sig_mask
        sig_with_implicit_one = sig | self.implicit_one if exp != 0 else sig
        return self.FloatData(sign, exp, sig, sig_with_implicit_one)

    def to_input_data(self, raw_float: int | str) -> dict[str, int]:
        (sign, exp, sig, sig_with_implicit_one) = self._decode_float(raw_float)
        # Matches FPU data_input_layout
        return {
            "sign": sign,
            "exp": exp,
            "sig": sig_with_implicit_one,
            "is_inf": ((exp == self.cv.max_exp) & (sig == 0)),
            "is_nan": ((exp == self.cv.max_exp) & (sig != 0)),
            "is_zero": ((exp == 0) & (sig == 0)),
        }

    def to_output_data(self, raw_float: int | str, errors: int | str) -> dict[str, int]:
        (sign, exp, _, sig_with_implicit_one) = self._decode_float(raw_float)
        # Matches FPU data_output_layout
        return {
            "sign": sign,
            "exp": exp,
            "sig": sig_with_implicit_one,
            "errors": int(errors, 16) if isinstance(errors, str) else errors,
        }
