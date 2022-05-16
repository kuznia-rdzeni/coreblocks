import unittest
from contextlib import contextmanager

from amaranth import *
from amaranth.sim import *
from coreblocks.transactions.lib import AdapterTrans


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

    def _set_inputs(self, values: dict, field=None):
        if field is None:
            field = self.adapter.data_in
        for name, value in values.items():
            if isinstance(value, dict):
                yield from self._set_inputs(value, getattr(field, name))
            else:
                yield getattr(field, name).eq(value)

    def _get_outputs(self, field=None):
        if field is None:
            field = self.adapter.data_out
        if isinstance(field, Signal):
            return (yield field)
        else:  # field is a Record
            result = {}
            for name, bits, _ in field.layout:
                result[name] = yield from self._get_outputs(getattr(field, name))
            return result

    # accept data as dict to be consistent with get()
    def put(self, data: dict):
        yield from self._enable()
        yield from self._set_inputs(data)
        yield
        yield from self._wait_until_done()
        yield from self._disable()

    def get(self):
        yield from self._enable()
        yield
        yield from self._wait_until_done()
        yield from self._disable()
        # return dict of all signal values in a record because amaranth's simulator can't read all
        # values of a Record in a single yield - it can only read Values (Signals)
        return (yield from self._get_outputs())

    def putget(self, data: dict):
        yield from self._enable()
        yield from self._set_inputs(data)
        yield
        yield from self._wait_until_done()
        yield from self._disable()
        return (yield from self._get_outputs())
