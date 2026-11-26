from coreblocks.func_blocks.fu.fpu.fpu_common import FPUParams
from test.func_blocks.fu.fpu.fpu_test_common import FloatData


class SignView:
    def __init__(self, gen: "FloatGenerator", sign: int):
        self._gen: FloatGenerator = gen
        self._sign: int = sign

    @property
    def zero(self) -> FloatData:
        return self._gen.zero(self._sign)

    @property
    def one(self) -> FloatData:
        return self._gen.one(self._sign)

    @property
    def inf(self) -> FloatData:
        return self._gen.inf(self._sign)

    @property
    def max_finite(self) -> FloatData:
        return self._gen.max_finite(self._sign)

    @property
    def min_normal(self) -> FloatData:
        return self._gen.min_normal(self._sign)

    def subnormal(self, sig: int) -> FloatData:
        return self._gen.subnormal(self._sign, sig)

    @property
    def min_subnormal(self) -> FloatData:
        return self._gen.min_subnormal(self._sign)

    @property
    def max_subnormal(self) -> FloatData:
        return self._gen.max_subnormal(self._sign)

    def nan(self, sig: int) -> FloatData:
        return self._gen.nan(self._sign, sig)

    def qnan(self, payload: int) -> FloatData:
        return self._gen.qnan(self._sign, payload)

    def snan(self, payload: int) -> FloatData:
        return self._gen.snan(self._sign, payload)


class FloatGenerator:
    def __init__(self, params: FPUParams):
        self.params: FPUParams = params
        self.plus: SignView = SignView(self, 0)
        self.minus: SignView = SignView(self, 1)
        self.exp_mask: int = (2**self.params.exp_width) - 1
        self.sig_mask: int = (2 ** (self.params.sig_width - 1)) - 1

    def zero(self, sign: int) -> FloatData:
        return FloatData(sign, 0, 0)

    def one(self, sign: int) -> FloatData:
        return FloatData(sign, self.exp_mask >> 1, 0)

    def inf(self, sign: int) -> FloatData:
        return FloatData(sign, self.exp_mask, 0)

    def max_finite(self, sign: int) -> FloatData:
        return FloatData(sign, self.exp_mask, 0)

    def min_normal(self, sign: int) -> FloatData:
        return FloatData(sign, 1, 0)

    def subnormal(self, sign: int, sig: int) -> FloatData:
        assert sig != 0
        return FloatData(sign, 0, sig)

    def min_subnormal(self, sign: int) -> FloatData:
        return self.subnormal(sign, 1)

    def max_subnormal(self, sign: int) -> FloatData:
        return self.subnormal(sign, self.sig_mask)

    def nan(self, sign: int, sig: int) -> FloatData:
        return FloatData(sign, self.exp_mask, sig)

    def qnan(self, sign: int, payload: int) -> FloatData:
        assert (payload & (self.sig_mask >> 1)) == payload
        return self.nan(sign, payload | (2 ** (self.params.sig_width - 2)))

    def snan(self, sign: int, payload: int) -> FloatData:
        assert (payload & (self.sig_mask >> 1)) == payload
        assert payload != 0
        return self.nan(sign, payload & (self.sig_mask >> 1))

    @property
    def common_floats(self) -> list[FloatData]:
        def get_common_with_sign(sign_view: SignView):
            return [
                sign_view.zero,
                sign_view.one,
                sign_view.inf,
                sign_view.max_finite,
                sign_view.min_normal,
                sign_view.min_subnormal,
                sign_view.max_subnormal,
                sign_view.qnan(0),
                sign_view.qnan(0x400),
                sign_view.snan(1),
                sign_view.snan(8),
            ]

        return get_common_with_sign(self.plus) + get_common_with_sign(self.minus)
