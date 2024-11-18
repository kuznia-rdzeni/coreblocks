from collections.abc import Generator, Iterable
from amaranth import *
from amaranth.lib.data import View, StructLayout
from amaranth.sim._async import SimulatorContext, TestbenchContext
from typing import Any, Optional

from transactron.lib import AdapterBase
from transactron.utils import ValueLike
from .functions import MethodData


__all__ = ["CallTrigger", "TestbenchIO"]


class CallTrigger:
    """A trigger which allows to call multiple methods and sample signals.

    The `call()` and `call_try()` methods on a `TestbenchIO` always wait at least one clock cycle. It follows
    that these methods can't be used to perform calls to multiple methods in a single clock cycle. Usually
    this is not a problem, as different methods can be called from different simulation processes. But in cases
    when more control over the time when different calls happen is needed, this trigger class allows to call
    many methods in a single clock cycle.
    """

    def __init__(
        self,
        sim: SimulatorContext,
        _calls: Iterable[ValueLike | tuple["TestbenchIO", Optional[dict[str, Any]]]] = (),
    ):
        """
        Parameters
        ----------
        sim: SimulatorContext
            Amaranth simulator context.
        """
        self.sim = sim
        self.calls_and_values: list[ValueLike | tuple[TestbenchIO, Optional[dict[str, Any]]]] = list(_calls)

    def sample(self, *values: "ValueLike | TestbenchIO"):
        """Sample a signal or a method result on a clock edge.

        Values are sampled like in standard Amaranth `TickTrigger`. Sampling a method result works like `call()`,
        but the method is not called - another process can do that instead. If the method was not called, the
        sampled value is `None`.

        Parameters
        ----------
        *values: ValueLike | TestbenchIO
            Value or method to sample.
        """
        new_calls_and_values: list[ValueLike | tuple["TestbenchIO", None]] = []
        for value in values:
            if isinstance(value, TestbenchIO):
                new_calls_and_values.append((value, None))
            else:
                new_calls_and_values.append(value)
        return CallTrigger(self.sim, (*self.calls_and_values, *new_calls_and_values))

    def call(self, tbio: "TestbenchIO", data: dict[str, Any] = {}, /, **kwdata):
        """Call a method and sample its result.

        Adds a method call to the trigger. The method result is sampled on a clock edge. If the call did not
        succeed, the sampled value is `None`.

        Parameters
        ----------
        tbio: TestbenchIO
            The method to call.
        data: dict[str, Any]
            Method call arguments stored in a dict.
        **kwdata: Any
            Method call arguments passed as keyword arguments. If keyword arguments are used,
            the `data` argument should not be provided.
        """
        if data and kwdata:
            raise TypeError("call() takes either a single dict or keyword arguments")
        return CallTrigger(self.sim, (*self.calls_and_values, (tbio, data or kwdata)))

    async def until_done(self) -> Any:
        """Wait until at least one of the calls succeeds.

        The `CallTrigger` normally acts like `TickTrigger`, e.g. awaiting on it advances the clock to the next
        clock edge. It is possible that none of the calls could not be performed, for example because the called
        methods were not enabled. In case we only want to focus on the cycles when one of the calls succeeded,
        `until_done` can be used. This works like `until()` in `TickTrigger`.
        """
        async for results in self:
            if any(res is not None for res in results):
                return results

    def __await__(self) -> Generator:
        only_calls = [t for t in self.calls_and_values if isinstance(t, tuple)]
        only_values = [t for t in self.calls_and_values if not isinstance(t, tuple)]

        for tbio, data in only_calls:
            if data is not None:
                tbio.call_init(self.sim, data)

        def layout_for(tbio: TestbenchIO):
            return StructLayout({"outputs": tbio.adapter.data_out.shape(), "done": 1})

        trigger = (
            self.sim.tick()
            .sample(*(View(layout_for(tbio), Cat(tbio.outputs, tbio.done)) for tbio, _ in only_calls))
            .sample(*only_values)
        )
        _, _, *results = yield from trigger.__await__()

        for tbio, data in only_calls:
            if data is not None:
                tbio.disable(self.sim)

        values_it = iter(results[len(only_calls) :])
        calls_it = (s.outputs if s.done else None for s in results[: len(only_calls)])

        def ret():
            for v in self.calls_and_values:
                if isinstance(v, tuple):
                    yield next(calls_it)
                else:
                    yield next(values_it)

        return tuple(ret())

    async def __aiter__(self):
        while True:
            yield await self


class TestbenchIO(Elaboratable):
    def __init__(self, adapter: AdapterBase):
        self.adapter = adapter

    def elaborate(self, platform):
        m = Module()
        m.submodules += self.adapter
        return m

    # Low-level operations

    def set_enable(self, sim: SimulatorContext, en):
        sim.set(self.adapter.en, 1 if en else 0)

    def enable(self, sim: SimulatorContext):
        self.set_enable(sim, True)

    def disable(self, sim: SimulatorContext):
        self.set_enable(sim, False)

    @property
    def done(self):
        return self.adapter.done

    @property
    def outputs(self):
        return self.adapter.data_out

    def set_inputs(self, sim: SimulatorContext, data):
        sim.set(self.adapter.data_in, data)

    def get_done(self, sim: TestbenchContext):
        return sim.get(self.adapter.done)

    def get_outputs(self, sim: TestbenchContext) -> MethodData:
        return sim.get(self.adapter.data_out)

    def sample_outputs(self, sim: SimulatorContext):
        return sim.tick().sample(self.adapter.data_out)

    def sample_outputs_until_done(self, sim: SimulatorContext):
        return self.sample_outputs(sim).until(self.adapter.done)

    def sample_outputs_done(self, sim: SimulatorContext):
        return sim.tick().sample(self.adapter.data_out, self.adapter.done)

    # Operations for AdapterTrans

    def call_init(self, sim: SimulatorContext, data={}, /, **kwdata):
        if data and kwdata:
            raise TypeError("call_init() takes either a single dict or keyword arguments")
        if not data:
            data = kwdata
        self.enable(sim)
        self.set_inputs(sim, data)

    def get_call_result(self, sim: TestbenchContext) -> Optional[MethodData]:
        if self.get_done(sim):
            return self.get_outputs(sim)
        return None

    async def call_result(self, sim: SimulatorContext) -> Optional[MethodData]:
        *_, data, done = await self.sample_outputs_done(sim)
        if done:
            return data
        return None

    async def call_do(self, sim: SimulatorContext) -> MethodData:
        *_, outputs = await self.sample_outputs_until_done(sim)
        self.disable(sim)
        return outputs

    async def call_try(self, sim: SimulatorContext, data={}, /, **kwdata) -> Optional[MethodData]:
        return (await CallTrigger(sim).call(self, data, **kwdata))[0]

    async def call(self, sim: SimulatorContext, data={}, /, **kwdata) -> MethodData:
        return (await CallTrigger(sim).call(self, data, **kwdata).until_done())[0]
