from dataclasses import dataclass

from amaranth import Signal
from amaranth.sim._async import ProcessContext

from transactron.utils.dependencies import DependencyContext, SimpleKey


__all__ = ["TicksKey", "make_tick_count_process"]


@dataclass(frozen=True)
class TicksKey(SimpleKey[Signal]):
    pass


def make_tick_count_process():
    ticks = Signal(64)
    DependencyContext.get().add_dependency(TicksKey(), ticks)

    async def process(sim: ProcessContext):
        async for _, _, ticks_val in sim.tick().sample(ticks):
            sim.set(ticks, ticks_val + 1)

    return process
