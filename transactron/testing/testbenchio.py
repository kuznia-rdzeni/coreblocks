from amaranth import *
from amaranth.sim import Settle, Passive, Tick
from typing import Optional, Callable

from amaranth_types import AnySimulatorContext
from transactron.lib import AdapterBase
from transactron.lib.adapters import Adapter
from transactron.utils import ValueLike, SignalBundle, mock_def_helper, assign
from transactron.utils._typing import RecordIntDictRet, RecordValueDict, RecordIntDict
from .functions import get_outputs, TestGen


class AsyncTestbenchIO(Elaboratable):
    def __init__(self, adapter: AdapterBase):
        self.adapter = adapter

    def elaborate(self, platform):
        m = Module()
        m.submodules += self.adapter
        return m

    # Low-level operations

    def set_enable(self, sim: AnySimulatorContext, en):
        sim.set(self.adapter.en, 1 if en else 0)

    def enable(self, sim: AnySimulatorContext):
        self.set_enable(sim, True)

    def disable(self, sim: AnySimulatorContext):
        self.set_enable(sim, False)

    @property
    def done(self):
        return self.adapter.done

    @property
    def outputs(self):
        return self.adapter.data_out

    def set_inputs(self, sim: AnySimulatorContext, data):
        sim.set(self.adapter.data_in, data)

    def sample_outputs(self, sim: AnySimulatorContext):
        return sim.tick().sample(self.adapter.data_out)

    def sample_outputs_until_done(self, sim: AnySimulatorContext):
        return self.sample_outputs(sim).until(self.adapter.done)

    def sample_outputs_done(self, sim: AnySimulatorContext):
        return sim.tick().sample(self.adapter.data_out, self.adapter.done)

    # Operations for AdapterTrans

    def call_init(self, sim: AnySimulatorContext, data={}, /, **kwdata):
        if data and kwdata:
            raise TypeError("call_init() takes either a single dict or keyword arguments")
        if not data:
            data = kwdata
        self.enable(sim)
        self.set_inputs(sim, data)

    async def call_result(self, sim: AnySimulatorContext):
        *_, data, done = await self.sample_outputs_done(sim)
        if done:
            return data
        return None

    async def call_do(self, sim: AnySimulatorContext):
        *_, outputs = await self.sample_outputs_until_done(sim)
        self.disable(sim)
        return outputs

    async def call_try(self, sim: AnySimulatorContext, data={}, /, **kwdata):
        if data and kwdata:
            raise TypeError("call_try() takes either a single dict or keyword arguments")
        if not data:
            data = kwdata
        self.call_init(sim, data)
        outputs = await self.call_result(sim)
        self.disable(sim)
        return outputs

    async def call(self, sim: AnySimulatorContext, data={}, /, **kwdata):
        if data and kwdata:
            raise TypeError("call() takes either a single dict or keyword arguments")
        if not data:
            data = kwdata
        self.call_init(sim, data)
        return await self.call_do(sim)


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
            yield Tick()

    def set_inputs(self, data: RecordValueDict = {}) -> TestGen[None]:
        yield from assign(self.adapter.data_in, data)

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
            yield Tick()
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
        yield Tick()
        outputs = yield from self.call_result()
        yield from self.disable()
        return outputs

    def call(self, data: RecordIntDict = {}, /, **kwdata: int | RecordIntDict) -> TestGen[RecordIntDictRet]:
        if data and kwdata:
            raise TypeError("call() takes either a single dict or keyword arguments")
        if not data:
            data = kwdata
        yield from self.call_init(data)
        yield Tick()
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
        validate_arguments: Optional[Callable[..., bool]] = None,
        extra_settle_count: int = 0,
    ) -> TestGen[None]:
        enable = enable or (lambda: True)
        yield from self.set_enable(enable())

        def handle_validate_arguments():
            if validate_arguments is not None:
                assert isinstance(self.adapter, Adapter)
                for a, r in self.adapter.validators:
                    ret_out = mock_def_helper(self, validate_arguments, (yield from get_outputs(a)))
                    yield r.eq(ret_out)
                for _ in range(extra_settle_count + 1):
                    yield Settle()

        # One extra Settle() required to propagate enable signal.
        for _ in range(extra_settle_count + 1):
            yield Settle()
        yield from handle_validate_arguments()
        while (arg := (yield from self.method_argument())) is None:
            yield Tick()

            yield from self.set_enable(enable())
            for _ in range(extra_settle_count + 1):
                yield Settle()
            yield from handle_validate_arguments()

        ret_out = mock_def_helper(self, function, arg)
        yield from self.method_return(ret_out or {})
        yield Tick()

    def method_handle_loop(
        self,
        function: Callable[..., Optional[RecordIntDict]],
        *,
        enable: Optional[Callable[[], bool]] = None,
        validate_arguments: Optional[Callable[..., bool]] = None,
        extra_settle_count: int = 0,
    ) -> TestGen[None]:
        yield Passive()
        while True:
            yield from self.method_handle(
                function, enable=enable, validate_arguments=validate_arguments, extra_settle_count=extra_settle_count
            )

    # Debug signals

    def debug_signals(self) -> SignalBundle:
        return self.adapter.debug_signals()
