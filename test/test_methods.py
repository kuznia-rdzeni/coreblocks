# amaranth: UnusedElaboratable=no
from amaranth import *
from amaranth.sim import *

from .common import TestCaseWithSimulator, TestbenchIO

from coreblocks.transactions import *
from coreblocks.transactions.lib import *

from parameterized import parameterized

from unittest import TestCase


class TestDefMethod(TestCaseWithSimulator):
    class TestModule(Elaboratable):
        def __init__(self, method_define_fn):
            self.transactionManager = TransactionManager()
            self.method = Method(
                o=[
                    ("foo1", 3),
                    ("foo2", [("bar1", 4), ("bar2", 6)]),
                ]
            )

            self.method_define_fn = method_define_fn

        def elaborate(self, platform):
            m = Module()

            self.method_define_fn(m, self.method)

            m.submodules += self.transactionManager

            # so that Amaranth allows us to use add_clock
            dummy = Signal()
            m.d.sync += dummy.eq(1)
            return m

    def do_test_definition(self, definer):
        with self.runSimulation(TestDefMethod.TestModule(definer)):
            pass

    def test_fields_valid1(self):
        def method_definer(m, method):
            @def_method(m, method)
            def _(arg):
                return {"foo1": Signal(3), "foo2": {"bar1": Signal(4), "bar2": Signal(6)}}

        self.do_test_definition(method_definer)

    def test_fields_valid2(self):
        def method_definer(m, method):
            rec = Record([("bar1", 4), ("bar2", 6)])

            @def_method(m, method)
            def _(arg):
                return {"foo1": Signal(3), "foo2": rec}

        self.do_test_definition(method_definer)

    def test_fields_invalid1(self):
        def method_definer(m, method):
            @def_method(m, method)
            def _(arg):
                return {"foo1": Signal(3), "baz": Signal(4)}

        with self.assertRaises(AttributeError):
            self.do_test_definition(method_definer)

    def test_fields_invalid2(self):
        def method_definer(m, method):
            @def_method(m, method)
            def _(arg):
                return {"foo1": Signal(3)}

        with self.assertRaises(KeyError):
            self.do_test_definition(method_definer)

    def test_fields_invalid3(self):
        def method_definer(m, method):
            @def_method(m, method)
            def _(arg):
                return {"foo1": {"baz1": Signal(), "baz2": Signal()}, "foo2": {"bar1": Signal(4), "bar2": Signal(6)}}

        with self.assertRaises(TypeError):
            self.do_test_definition(method_definer)


class AdapterCircuit(Elaboratable):
    def __init__(self, module, methods):
        self.module = module
        self.methods = methods

    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

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

        m.submodules.quadruple = self.quadruple
        m.submodules.tb = self.tb = TestbenchIO(AdapterTrans(self.quadruple.quadruple))
        # so that Amaranth allows us to use add_clock
        dummy = Signal()
        m.d.sync += dummy.eq(1)

        return tm


class Quadruple2(Elaboratable):
    def __init__(self):
        self.quadruple = Method(i=WIDTH, o=WIDTH)

    def elaborate(self, platform):
        m = Module()

        m.submodules.sub = Quadruple()

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
            sim.add_sync_process(process)


class ConditionalCallCircuit(Elaboratable):
    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        meth = Method(i=1)

        m.submodules.tb = self.tb = TestbenchIO(AdapterTrans(meth))
        m.submodules.out = self.out = TestbenchIO(Adapter())

        @def_method(m, meth)
        def _(arg):
            with m.If(arg):
                self.out.adapter.iface(m)

        # so that Amaranth allows us to use add_clock
        dummy = Signal()
        m.d.sync += dummy.eq(1)

        return tm


class ConditionalMethodCircuit1(Elaboratable):
    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        meth = Method()

        self.ready = Signal()
        m.submodules.tb = self.tb = TestbenchIO(AdapterTrans(meth))

        @def_method(m, meth, ready=self.ready)
        def _(arg):
            pass

        # so that Amaranth allows us to use add_clock
        dummy = Signal()
        m.d.sync += dummy.eq(1)
        return tm


class ConditionalMethodCircuit2(Elaboratable):
    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        meth = Method()

        self.ready = Signal()
        m.submodules.tb = self.tb = TestbenchIO(AdapterTrans(meth))

        with m.If(self.ready):

            @def_method(m, meth)
            def _(arg):
                pass

        # so that Amaranth allows us to use add_clock
        dummy = Signal()
        m.d.sync += dummy.eq(1)
        return tm


class ConditionalTransactionCircuit1(Elaboratable):
    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        self.ready = Signal()
        m.submodules.tb = self.tb = TestbenchIO(Adapter())

        with tm.transactionContext():
            with Transaction().body(m, request=self.ready):
                self.tb.adapter.iface(m)

        # so that Amaranth allows us to use add_clock
        dummy = Signal()
        m.d.sync += dummy.eq(1)
        return tm


class ConditionalTransactionCircuit2(Elaboratable):
    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        self.ready = Signal()
        m.submodules.tb = self.tb = TestbenchIO(Adapter())

        with tm.transactionContext():
            with m.If(self.ready):
                with Transaction().body(m):
                    self.tb.adapter.iface(m)

        # so that Amaranth allows us to use add_clock
        dummy = Signal()
        m.d.sync += dummy.eq(1)
        return tm


class TestConditionals(TestCaseWithSimulator):
    def testConditionalCall(self):
        circ = ConditionalCallCircuit()

        def process():
            yield from circ.out.disable()
            yield from circ.tb.call_init({"data": 0})
            yield Settle()
            self.assertFalse((yield from circ.out.done()))
            self.assertFalse((yield from circ.tb.done()))

            yield from circ.out.enable()
            yield Settle()
            self.assertFalse((yield from circ.out.done()))
            self.assertTrue((yield from circ.tb.done()))

            yield from circ.tb.call_init({"data": 1})
            yield Settle()
            self.assertTrue((yield from circ.out.done()))
            self.assertTrue((yield from circ.tb.done()))

            # the argument is still 1 but the method is not called
            yield from circ.tb.disable()
            yield Settle()
            self.assertFalse((yield from circ.out.done()))
            self.assertFalse((yield from circ.tb.done()))

        with self.runSimulation(circ) as sim:
            sim.add_sync_process(process)

    @parameterized.expand(
        [
            (ConditionalMethodCircuit1(),),
            (ConditionalMethodCircuit2(),),
            (ConditionalTransactionCircuit1(),),
            (ConditionalTransactionCircuit2(),),
        ]
    )
    def testConditional(self, circ):
        def process():
            yield from circ.tb.enable()
            yield circ.ready.eq(0)
            yield Settle()
            self.assertFalse((yield from circ.tb.done()))

            yield circ.ready.eq(1)
            yield Settle()
            self.assertTrue((yield from circ.tb.done()))

        with self.runSimulation(circ) as sim:
            sim.add_sync_process(process)
