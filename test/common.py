import unittest
from contextlib import contextmanager
from typing import Union

from amaranth import *
from amaranth.sim import *
from coreblocks.transactions.lib import AdapterTrans


def set_inputs(values: dict, field: Record):
    for name, value in values.items():
        if isinstance(value, dict):
            yield from set_inputs(value, getattr(field, name))
        else:
            yield getattr(field, name).eq(value)


def get_outputs(field: Union["Record", "Signal"]):
    if isinstance(field, Signal):
        return (yield field)
    else:  # field is a Record
        # return dict of all signal values in a record because amaranth's simulator can't read all
        # values of a Record in a single yield - it can only read Values (Signals)
        result = {}
        for name, bits, _ in field.layout:
            result[name] = yield from get_outputs(getattr(field, name))
        return result


class TestCaseWithSimulator(unittest.TestCase):
    @contextmanager
    def runSimulation(self, module):
        sim = Simulator(module)
        yield sim
        with sim.write_vcd("test.vcd", "test.gtkw"):
            sim.run()


class TestbenchIO(Elaboratable):
    def __init__(self, *args, **kwargs):
        self.adapter = AdapterTrans(*args, **kwargs)

    def elaborate(self, platform):
        m = Module()
        m.submodules += self.adapter
        return m

    def _enable(self):
        yield self.adapter.en.eq(1)

    def _disable(self):
        yield self.adapter.en.eq(0)

    def _wait_until_done(self):
        while (yield self.adapter.done) != 1:
            yield

    def call_init(self, data: dict = {}):
        yield from self._enable()
        yield from set_inputs(data, self.adapter.data_in)

    def call_do(self):
        yield from self._wait_until_done()
        yield from self._disable()
        return (yield from get_outputs(self.adapter.data_out))

    def call(self, data: dict = {}):
        yield from self.call_init(data)
        yield
        return (yield from self.call_do())
