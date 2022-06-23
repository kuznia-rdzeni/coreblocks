from amaranth import *
from amaranth.sim import Passive

from coreblocks.transactions import TransactionModule, Method, def_method
from coreblocks.transactions.lib import AdapterTrans


from .common import TestCaseWithSimulator, TestbenchIO


class Echo(Elaboratable):
    def __init__(self):
        self.data_bits = 8

        self.layout_in = [("data", self.data_bits)]
        self.layout_out = [("data", self.data_bits)]

        self.action = Method(i=self.layout_in, o=self.layout_out)

    def elaborate(self, platform):
        m = Module()

        # so that Amaranth allows us to use add_clock
        dummy = Signal()
        m.d.sync += dummy.eq(1)

        @def_method(m, self.action, ready=C(1))
        def _(arg):
            return arg

        return m


class Consumer(Elaboratable):
    def __init__(self, const):
        self.const = const
        self.data_bits = 8

        self.layout_in = [("data", self.data_bits)]
        self.layout_out = []

        self.action = Method(i=self.layout_in, o=self.layout_out)

    def elaborate(self, platform):
        m = Module()

        # so that Amaranth allows us to use add_clock
        dummy = Signal()
        m.d.sync += dummy.eq(1)

        @def_method(m, self.action, ready=C(1))
        def _(arg):
            return self.const

        return m


class TestElaboratable(Elaboratable):
    def __init__(self):
        self.m = Module()
        self.tm = TransactionModule(self.m)

        self.echo = Echo()
        self.consumers = [Consumer(x) for x in [None, 0, 1, 5]]
        self.io_echo = TestbenchIO(AdapterTrans(self.echo.action))
        self.io_consume = [TestbenchIO(AdapterTrans(c.action)) for c in self.consumers]

    def elaborate(self, platform):
        m = self.m

        m.submodules.echo = self.echo
        m.submodules.io_echo = self.io_echo
        m.submodules += self.consumers
        m.submodules += self.io_consume

        return self.tm


class TestAdapterTrans(TestCaseWithSimulator):
    def proc(self):
        for do_consume in self.t.io_consume:
            for _ in range(3):
                # this would previously timeout if the output layout was empty (as is in this case)
                print((yield from do_consume.call()))
        for expected in [4, 1, 0]:
            obtained = (yield from self.t.io_echo.call({"data": expected}))["data"]
            self.assertEqual(expected, obtained)

    def test_single(self):
        self.t = t = TestElaboratable()

        with self.runSimulation(t, max_cycles=100) as sim:
            sim.add_sync_process(self.proc)
