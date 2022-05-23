# amaranth: UnusedElaboratable=no
from amaranth import *
from amaranth.sim import *

from .common import TestCaseWithSimulator, TestbenchIO

from coreblocks.transactions import *
from coreblocks.transactions.lib import *

from unittest import TestCase


class AdapterCircuit(Elaboratable):
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
    def assert_re(self, msg, m):
        with self.assertRaisesRegex(RuntimeError, msg):
            Fragment.get(m, platform=None)

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

        self.assert_re("called twice", Twice())

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
        self.assert_re("called twice", AdapterCircuit(m, [m.meth4]))

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
        self.assert_re("called twice", AdapterCircuit(m, [m.meth1]))

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
        self.assert_re("called twice", AdapterCircuit(m, [m.meth1]))

    def testRedefine(self):
        class Redefine(Elaboratable):
            def elaborate(self, platform):
                m = Module()
                meth = Method()

                with meth.body(m):
                    pass

                with meth.body(m):
                    pass

        self.assert_re("already defined", Redefine())

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

        self.assert_re("not defined", Circuit())


WIDTH = 8


class Quadruple(Elaboratable):
    def __init__(self):
        self.id = Method(i=WIDTH, o=WIDTH)
        self.double = Method(i=WIDTH, o=WIDTH)
        self.quadruple = Method(i=WIDTH, o=WIDTH)

    def elaborate(self, platform):
        m = Module()

        @def_method(m, self.id)
        def _(arg):
            return arg

        @def_method(m, self.double)
        def _(arg):
            return self.id(m, arg) * 2

        @def_method(m, self.quadruple)
        def _(arg):
            return self.double(m, arg) * 2

        return m


class QuadrupleCircuit(Elaboratable):
    def __init__(self, quadruple):
        self.quadruple = quadruple

    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        with tm.transactionContext():
            m.submodules.quadruple = self.quadruple
            m.submodules.tb = self.tb = TestbenchIO(AdapterTrans(self.quadruple.quadruple))
            # so that Amaranth allows us to use add_clock
            dummy = Signal()
            m.d.sync += dummy.eq(1)

        return tm


class QuadrupleSub(Elaboratable):
    def __init__(self):
        self.id = Method(i=WIDTH, o=WIDTH)
        self.double = Method(i=WIDTH, o=WIDTH)

    def elaborate(self, platform):
        m = Module()

        @def_method(m, self.id)
        def _(arg):
            return arg

        @def_method(m, self.double)
        def _(arg):
            return 2 * self.id(m, arg)

        return m


class Quadruple2(Elaboratable):
    def __init__(self):
        self.quadruple = Method(i=WIDTH, o=WIDTH)

    def elaborate(self, platform):
        m = Module()

        m.submodules.sub = QuadrupleSub()

        @def_method(m, self.quadruple)
        def _(arg):
            return 2 * m.submodules.sub.double(m, arg)

        return m


class TestQuadrupleCircuits(TestCaseWithSimulator):
    def test(self):
        self.work(QuadrupleCircuit(Quadruple()))
        self.work(QuadrupleCircuit(Quadruple2()))

    def work(self, circ):
        def process():
            for n in range(1 << (WIDTH - 2)):
                out = yield from circ.tb.call({"data": n})
                self.assertEqual(out["data"], n * 4)

        with self.runSimulation(circ) as sim:
            sim.add_clock(1e-6)
            sim.add_sync_process(process)
