# amaranth: UnusedElaboratable=no
from amaranth import *
from amaranth.sim import *

from .common import TestCaseWithSimulator

from coreblocks.transactions import *
from coreblocks.transactions.lib import *

from unittest import TestCase


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
    def __init__(self, four):
        self.four = four
        self.en = Signal()
        self.out = Signal(4)

    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        with tm.transactionContext():
            m.submodules.four = four = self.four
            m.submodules.out = out = AdapterTrans(four.four)
            m.d.comb += out.en.eq(C(1))
            m.d.comb += four.en.eq(self.en)
            m.d.comb += self.out.eq(out.data_out)

        return tm


# from amaranth.back import verilog
# m = FourCircuit()
# print(verilog.convert(m, ports=[m.en, m.out]))


def elab(module):
    return Fragment.get(module, platform=None)


class MultiAdapter(Elaboratable):
    def __init__(self, module, methods):
        self.module = module
        self.methods = methods

    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        with tm.transactionContext():
            m.submodules += self.module
            for method in self.methods:
                m.submodules += AdapterTrans(method)

        return tm


class TestInvalidMethods(TestCase):
    def testTwice(self):
        class Twice(Elaboratable):
            def __init__(self):
                self.meth1 = Method()
                self.meth2 = Method()

            def elaborate(self, platform):
                m = Module()

                with self.meth1.body(m):
                    pass

                with self.meth2.body(m):
                    self.meth1(m)
                    self.meth1(m)

                return m

        m = Twice()
        self.assertRaisesRegex(RuntimeError, "called twice", lambda: elab(MultiAdapter(m, [m.meth2])))

    def testDiamond(self):
        class Diamond(Elaboratable):
            def __init__(self):
                self.meth1 = Method()
                self.meth2 = Method()
                self.meth3 = Method()
                self.meth4 = Method()

            def elaborate(self, platform):
                m = Module()

                with self.meth1.body(m):
                    pass

                with self.meth2.body(m):
                    self.meth1(m)

                with self.meth3.body(m):
                    self.meth1(m)

                with self.meth4.body(m):
                    self.meth2(m)
                    self.meth3(m)

                return m

        m = Diamond()
        self.assertRaisesRegex(RuntimeError, "called twice", lambda: elab(MultiAdapter(m, [m.meth4])))

    def testLoop(self):
        class Loop(Elaboratable):
            def __init__(self):
                self.meth1 = Method()

            def elaborate(self, platform):
                m = Module()

                with self.meth1.body(m):
                    self.meth1(m)

                return m

        m = Loop()
        self.assertRaisesRegex(RuntimeError, "called twice", lambda: elab(MultiAdapter(m, [m.meth1])))

    def testCycle(self):
        class Cycle(Elaboratable):
            def __init__(self):
                self.meth1 = Method()
                self.meth2 = Method()

            def elaborate(self, platform):
                m = Module()

                with self.meth1.body(m):
                    self.meth2(m)

                with self.meth2.body(m):
                    self.meth1(m)

                return m

        m = Cycle()
        self.assertRaisesRegex(RuntimeError, "called twice", lambda: elab(MultiAdapter(m, [m.meth1])))

    def testRedefine(self):
        class Redefine(Elaboratable):
            def elaborate(self, platform):
                m = Module()
                meth = Method()

                with meth.body(m):
                    pass

                with meth.body(m):
                    pass

        self.assertRaisesRegex(RuntimeError, "already defined", lambda: Redefine().elaborate(platform=None))

    def testUndefinedInTrans(self):
        class Undefined(Elaboratable):
            def __init__(self):
                self.meth = Method(i=1)

            def elaborate(self, platform):
                return Module()

        class Circuit(Elaboratable):
            def elaborate(self, platform):
                m = Module()
                tm = TransactionModule(m)

                with tm.transactionContext():
                    m.submodules.undefined = undefined = Undefined()
                    m.submodules.adapter = AdapterTrans(undefined.meth)

                return tm

        self.assertRaisesRegex(RuntimeError, "not defined", lambda: Fragment.get(Circuit(), platform=None))


class Submodule(Elaboratable):
    def __init__(self):
        self.methB = Method(o=4)
        self.methC = Method(o=4)

    def elaborate(self, platform):
        m = Module()

        with self.methC.body(m, out=C(1)):
            pass

        outB = Signal(4)
        with self.methB.body(m, out=outB):
            m.d.comb += outB.eq(2 * self.methC(m))

        return m


class FourSub(Elaboratable):
    def __init__(self):
        self.four = Method(o=4)
        self.en = Signal()
        self.out = Signal(4)

    def elaborate(self, platform):
        m = Module()

        m.submodules.sub = Submodule()

        with self.four.body(m, ready=self.en, out=self.out):
            m.d.comb += self.out.eq(2 * m.submodules.sub.methB(m))

        return m


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
        self.work(FourCircuit(Four()))
        self.work(FourCircuit(FourSub()))

    def work(self, circ):
        self.circ = circ

        def process():
            for i in range(10):
                yield from self.sim_step()

        with self.runSimulation(self.circ) as sim:
            # sim.add_clock(1e-6)
            # sim.add_sync_process(process)
            sim.add_process(process)
