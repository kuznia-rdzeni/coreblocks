import unittest
import os
from contextlib import contextmanager
from typing import Union

from amaranth import *
from amaranth.sim import *
from coreblocks.transactions.lib import AdapterBase


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
    def runSimulation(self, module, deadline=1e-2):
        test_name = unittest.TestCase.id(self)

        sim = Simulator(module)
        yield sim

        if "__COREBLOCKS_DUMP_TRACES" in os.environ:
            traces_dir = "test/__traces__"
            os.makedirs(traces_dir, exist_ok=True)
            with sim.write_vcd(f"{traces_dir}/{test_name}.vcd", f"{traces_dir}/{test_name}.gtkw"):
                self.run_sim_limited(sim, deadline)
        else:
            self.run_sim_limited(sim, deadline)

    def run_sim_limited(self, sim, deadline):
        sim.run_until(deadline)
        self.assertFalse(sim.advance(), "Simulation time limit exceeded")


class TestbenchIO(Elaboratable):
    def __init__(self, adapter: AdapterBase):
        self.adapter = adapter

    def elaborate(self, platform):
        m = Module()
        m.submodules += self.adapter
        return m

    def enable(self):
        yield self.adapter.en.eq(1)

    def disable(self):
        yield self.adapter.en.eq(0)

    def done(self):
        return (yield self.adapter.done)

    def _wait_until_done(self):
        while (yield self.adapter.done) != 1:
            yield

    def call_init(self, data: dict = {}):
        yield from self.enable()
        yield from set_inputs(data, self.adapter.data_in)

    def call_result(self):
        if (yield self.adapter.done):
            return (yield from get_outputs(self.adapter.data_out))
        return None

    def call_do(self):
        while not (outputs := (yield from self.call_result())):
            yield
        yield from self.disable()
        return outputs

    def call(self, data: dict = {}):
        yield from self.call_init(data)
        yield
        return (yield from self.call_do())
