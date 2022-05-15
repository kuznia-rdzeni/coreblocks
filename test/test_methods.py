from amaranth import *
from amaranth.sim import *

from .common import TestCaseWithSimulator

from coreblocks.transactions import *
from coreblocks.transactions.lib import *


class Four(Elaboratable):
    def __init__(self):
        self.one = Method(o=4)
        self.two = Method(o=4)
        self.four = Method(o=4)
        self.en = Signal()

    def elaborate(self, platform):
        m = Module()

        with self.one.body(m, out=C(1)):
            pass

        two_out = Signal(4)
        with self.two.body(m, out=two_out):
            m.d.comb += two_out.eq(2 * self.one(m))

        four_out = Signal(4)
        with self.four.body(m, ready=self.en, out=four_out):
            m.d.comb += four_out.eq(2 * self.two(m))

        return m


class FourCircuit(Elaboratable):
    def __init__(self):
        self.en = Signal()
        self.out = Signal(4)

    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        with tm.transactionContext():
            m.submodules.four = four = Four()
            m.submodules.out = out = AdapterTrans(four.four, o=4)
            m.d.comb += out.en.eq(C(1))
            m.d.comb += four.en.eq(self.en)
            m.d.comb += self.out.eq(out.data_out)

        return tm


# from amaranth.back import verilog
# m = FourCircuit()
# print(verilog.convert(m, ports=[m.en, m.out]))


class TestFourCircuit(TestCaseWithSimulator):
    def sim_step(self):
        yield self.circ.en.eq(1)
        # yield
        # yield
        yield Settle()
        self.assertEqual((yield self.circ.out), 4)

        yield self.circ.en.eq(0)
        # yield
        # yield
        yield Settle()
        self.assertEqual((yield self.circ.out), 0)

    def test(self):
        self.circ = FourCircuit()

        def process():
            for i in range(10):
                yield from self.sim_step()

        with self.runSimulation(self.circ) as sim:
            # sim.add_clock(1e-6)
            # sim.add_sync_process(process)
            sim.add_process(process)
