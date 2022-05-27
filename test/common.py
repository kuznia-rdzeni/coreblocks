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
    def runSimulation(self, module):
        test_name = unittest.TestCase.id(self)

        sim = Simulator(module)
        yield sim

        if "__COREBLOCKS_DUMP_TRACES" in os.environ:
            traces_dir = "test/__traces__"
            vcd_file = f"{traces_dir}/{test_name}.vcd"

            gtkw_file = None
            if os.environ["__COREBLOCKS_DUMP_TRACES"] == "gtkwave":
                gtkw_file = f"{traces_dir}/{test_name}.gtkw"

            os.makedirs(traces_dir, exist_ok=True)
            with sim.write_vcd(vcd_file=vcd_file, gtkw_file=gtkw_file):
                sim.run()
        else:
            sim.run()


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
