from amaranth import *

from coreblocks.transactions import TransactionModule, Method, def_method
from coreblocks.transactions.lib import AdapterTrans


from ..common import TestCaseWithSimulator, TestbenchIO, data_layout


class Echo(Elaboratable):
    def __init__(self):
        self.data_bits = 8

        self.layout_in = data_layout(self.data_bits)
        self.layout_out = data_layout(self.data_bits)

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
    def __init__(self):
        self.data_bits = 8

        self.layout_in = data_layout(self.data_bits)
        self.layout_out = []

        self.action = Method(i=self.layout_in, o=self.layout_out)

    def elaborate(self, platform):
        m = Module()

        # so that Amaranth allows us to use add_clock
        dummy = Signal()
        m.d.sync += dummy.eq(1)

        @def_method(m, self.action, ready=C(1))
        def _(arg):
            return None

        return m


class TestElaboratable(Elaboratable):
    def __init__(self):

        self.echo = Echo()
        self.consumer = Consumer()
        self.io_echo = TestbenchIO(AdapterTrans(self.echo.action))
        self.io_consume = TestbenchIO(AdapterTrans(self.consumer.action))

    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        m.submodules.echo = self.echo
        m.submodules.io_echo = self.io_echo
        m.submodules.consumer = self.consumer
        m.submodules.io_consume = self.io_consume

        return tm


class TestAdapterTrans(TestCaseWithSimulator):
    def proc(self):
        for _ in range(3):
            # this would previously timeout if the output layout was empty (as is in this case)
            yield from self.t.io_consume.call()
        for expected in [4, 1, 0]:
            obtained = (yield from self.t.io_echo.call({"data": expected}))["data"]
            self.assertEqual(expected, obtained)

    def test_single(self):
        self.t = t = TestElaboratable()

        with self.run_simulation(t, max_cycles=100) as sim:
            sim.add_sync_process(self.proc)
