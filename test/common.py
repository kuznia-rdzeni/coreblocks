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

    def _set_input(self, name, value):
        yield getattr(self.adapter.data_in, name).eq(value)

    def _get_output(self, name):
        return (yield getattr(self.adapter.data_out, name))

    # accept data as dict to be consistent with get()
    def put(self, data: dict):
        yield from self._enable()
        for name, value in data.items():
            yield from self._set_input(name, value)
        yield
        yield from self._wait_until_done()
        yield from self._disable()

    def get(self):
        yield from self._enable()
        yield
        yield from self._wait_until_done()
        yield from self._disable()
        # return dict of all signal values in a record because amaranth doesn't support yielding records -
        # - they're neither Value nor Statement and amaranth implementation only supports these two
        result = {}
        for name, _, _ in self.adapter.output_fmt:
            result[name] = yield from self._get_output(name)
        return result
