from amaranth import *
from amaranth.sim import Settle, Passive
from typing import Optional, Callable
from transactron.lib import AdapterBase
from transactron.core import ValueLike, SignalBundle
from transactron._utils import mock_def_helper
from transactron.utils._typing import RecordIntDictRet, RecordValueDict, RecordIntDict
from .functions import set_inputs, get_outputs, TestGen


class TestbenchIO(Elaboratable):
    def __init__(self, adapter: AdapterBase):
        self.adapter = adapter

    def elaborate(self, platform):
        m = Module()
        m.submodules += self.adapter
        return m

    # Low-level operations

    def set_enable(self, en) -> TestGen[None]:
        yield self.adapter.en.eq(1 if en else 0)

    def enable(self) -> TestGen[None]:
        yield from self.set_enable(True)

    def disable(self) -> TestGen[None]:
        yield from self.set_enable(False)

    def done(self) -> TestGen[int]:
        return (yield self.adapter.done)

    def wait_until_done(self) -> TestGen[None]:
        while (yield self.adapter.done) != 1:
            yield

    def set_inputs(self, data: RecordValueDict = {}) -> TestGen[None]:
        yield from set_inputs(data, self.adapter.data_in)

    def get_outputs(self) -> TestGen[RecordIntDictRet]:
        return (yield from get_outputs(self.adapter.data_out))

    # Operations for AdapterTrans

    def call_init(self, data: RecordValueDict = {}, /, **kwdata: ValueLike | RecordValueDict) -> TestGen[None]:
        if data and kwdata:
            raise TypeError("call_init() takes either a single dict or keyword arguments")
        if not data:
            data = kwdata
        yield from self.enable()
        yield from self.set_inputs(data)

    def call_result(self) -> TestGen[Optional[RecordIntDictRet]]:
        if (yield from self.done()):
            return (yield from self.get_outputs())
        return None

    def call_do(self) -> TestGen[RecordIntDict]:
        while (outputs := (yield from self.call_result())) is None:
            yield
        yield from self.disable()
        return outputs

    def call_try(
        self, data: RecordIntDict = {}, /, **kwdata: int | RecordIntDict
    ) -> TestGen[Optional[RecordIntDictRet]]:
        if data and kwdata:
            raise TypeError("call_try() takes either a single dict or keyword arguments")
        if not data:
            data = kwdata
        yield from self.call_init(data)
        yield
        outputs = yield from self.call_result()
        yield from self.disable()
        return outputs

    def call(self, data: RecordIntDict = {}, /, **kwdata: int | RecordIntDict) -> TestGen[RecordIntDictRet]:
        if data and kwdata:
            raise TypeError("call() takes either a single dict or keyword arguments")
        if not data:
            data = kwdata
        yield from self.call_init(data)
        yield
        return (yield from self.call_do())

    # Operations for Adapter

    def method_argument(self) -> TestGen[Optional[RecordIntDictRet]]:
        return (yield from self.call_result())

    def method_return(self, data: RecordValueDict = {}) -> TestGen[None]:
        yield from self.set_inputs(data)

    def method_handle(
        self,
        function: Callable[..., Optional[RecordIntDict]],
        *,
        enable: Optional[Callable[[], bool]] = None,
        extra_settle_count: int = 0,
    ) -> TestGen[None]:
        enable = enable or (lambda: True)
        yield from self.set_enable(enable())

        # One extra Settle() required to propagate enable signal.
        for _ in range(extra_settle_count + 1):
            yield Settle()
        while (arg := (yield from self.method_argument())) is None:
            yield
            yield from self.set_enable(enable())
            for _ in range(extra_settle_count + 1):
                yield Settle()

        ret_out = mock_def_helper(self, function, arg)
        yield from self.method_return(ret_out or {})
        yield

    def method_handle_loop(
        self,
        function: Callable[..., Optional[RecordIntDict]],
        *,
        enable: Optional[Callable[[], bool]] = None,
        extra_settle_count: int = 0,
    ) -> TestGen[None]:
        yield Passive()
        while True:
            yield from self.method_handle(function, enable=enable, extra_settle_count=extra_settle_count)

    # Debug signals

    def debug_signals(self) -> SignalBundle:
        return self.adapter.debug_signals()
