import random
from amaranth import *
from amaranth.sim import *

from transactron.testing import TestCaseWithSimulator, TestbenchIO, data_layout

from transactron import *
from transactron.utils import MethodStruct
from transactron.lib import *

from parameterized import parameterized

from unittest import TestCase


class TestDefMethod(TestCaseWithSimulator):
    class CircuitTestModule(Elaboratable):
        def __init__(self, method_definition):
            self.method = Method(
                i=[("foo1", 3), ("foo2", [("bar1", 4), ("bar2", 6)])],
                o=[("foo1", 3), ("foo2", [("bar1", 4), ("bar2", 6)])],
            )

            self.method_definition = method_definition

        def elaborate(self, platform):
            m = TModule()
            m._MustUse__silence = True  # type: ignore

            def_method(m, self.method)(self.method_definition)

            return m

    def do_test_definition(self, definer):
        with self.run_simulation(TestDefMethod.CircuitTestModule(definer)):
            pass

    def test_fields_valid1(self):
        def definition(arg):
            return {"foo1": Signal(3), "foo2": {"bar1": Signal(4), "bar2": Signal(6)}}

        self.do_test_definition(definition)

    def test_fields_valid2(self):
        rec = Signal(from_method_layout([("bar1", 4), ("bar2", 6)]))

        def definition(arg):
            return {"foo1": Signal(3), "foo2": rec}

        self.do_test_definition(definition)

    def test_fields_valid3(self):
        def definition(arg):
            return arg

        self.do_test_definition(definition)

    def test_fields_valid4(self):
        def definition(arg: MethodStruct):
            return arg

        self.do_test_definition(definition)

    def test_fields_valid5(self):
        def definition(**arg):
            return arg

        self.do_test_definition(definition)

    def test_fields_valid6(self):
        def definition(foo1, foo2):
            return {"foo1": foo1, "foo2": foo2}

        self.do_test_definition(definition)

    def test_fields_valid7(self):
        def definition(foo1, **arg):
            return {"foo1": foo1, "foo2": arg["foo2"]}

        self.do_test_definition(definition)

    def test_fields_invalid1(self):
        def definition(arg):
            return {"foo1": Signal(3), "baz": Signal(4)}

        with self.assertRaises(KeyError):
            self.do_test_definition(definition)

    def test_fields_invalid2(self):
        def definition(arg):
            return {"foo1": Signal(3)}

        with self.assertRaises(KeyError):
            self.do_test_definition(definition)

    def test_fields_invalid3(self):
        def definition(arg):
            return {"foo1": {"baz1": Signal(), "baz2": Signal()}, "foo2": {"bar1": Signal(4), "bar2": Signal(6)}}

        with self.assertRaises(TypeError):
            self.do_test_definition(definition)

    def test_fields_invalid4(self):
        def definition(arg: Value):
            return arg

        with self.assertRaises(TypeError):
            self.do_test_definition(definition)

    def test_fields_invalid5(self):
        def definition(foo):
            return foo

        with self.assertRaises(TypeError):
            self.do_test_definition(definition)

    def test_fields_invalid6(self):
        def definition(foo1):
            return {"foo1": foo1, "foo2": {"bar1": Signal(4), "bar2": Signal(6)}}

        with self.assertRaises(TypeError):
            self.do_test_definition(definition)


class AdapterCircuit(Elaboratable):
    def __init__(self, module, methods):
        self.module = module
        self.methods = methods

    def elaborate(self, platform):
        m = TModule()

        m.submodules += self.module
        for method in self.methods:
            m.submodules += AdapterTrans(method)

        return m


class TestInvalidMethods(TestCase):
    def assert_re(self, msg, m):
        with self.assertRaisesRegex(RuntimeError, msg):
            Fragment.get(TransactionModule(m), platform=None)

    def test_twice(self):
        class Twice(Elaboratable):
            def __init__(self):
                self.meth1 = Method()
                self.meth2 = Method()

            def elaborate(self, platform):
                m = TModule()
                m._MustUse__silence = True  # type: ignore

                with self.meth1.body(m):
                    pass

                with self.meth2.body(m):
                    self.meth1(m)
                    self.meth1(m)

                return m

        self.assert_re("called twice", Twice())

    def test_twice_cond(self):
        class Twice(Elaboratable):
            def __init__(self):
                self.meth1 = Method()
                self.meth2 = Method()

            def elaborate(self, platform):
                m = TModule()
                m._MustUse__silence = True  # type: ignore

                with self.meth1.body(m):
                    pass

                with self.meth2.body(m):
                    with m.If(1):
                        self.meth1(m)
                    with m.Else():
                        self.meth1(m)

                return m

        Fragment.get(TransactionModule(Twice()), platform=None)

    def test_diamond(self):
        class Diamond(Elaboratable):
            def __init__(self):
                self.meth1 = Method()
                self.meth2 = Method()
                self.meth3 = Method()
                self.meth4 = Method()

            def elaborate(self, platform):
                m = TModule()

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

    def test_loop(self):
        class Loop(Elaboratable):
            def __init__(self):
                self.meth1 = Method()

            def elaborate(self, platform):
                m = TModule()

                with self.meth1.body(m):
                    self.meth1(m)

                return m

        m = Loop()
        self.assert_re("called twice", AdapterCircuit(m, [m.meth1]))

    def test_cycle(self):
        class Cycle(Elaboratable):
            def __init__(self):
                self.meth1 = Method()
                self.meth2 = Method()

            def elaborate(self, platform):
                m = TModule()

                with self.meth1.body(m):
                    self.meth2(m)

                with self.meth2.body(m):
                    self.meth1(m)

                return m

        m = Cycle()
        self.assert_re("called twice", AdapterCircuit(m, [m.meth1]))

    def test_redefine(self):
        class Redefine(Elaboratable):
            def elaborate(self, platform):
                m = TModule()
                m._MustUse__silence = True  # type: ignore

                meth = Method()

                with meth.body(m):
                    pass

                with meth.body(m):
                    pass

        self.assert_re("already defined", Redefine())

    def test_undefined_in_trans(self):
        class Undefined(Elaboratable):
            def __init__(self):
                self.meth = Method(i=data_layout(1))

            def elaborate(self, platform):
                return TModule()

        class Circuit(Elaboratable):
            def elaborate(self, platform):
                m = TModule()

                m.submodules.undefined = undefined = Undefined()
                m.submodules.adapter = AdapterTrans(undefined.meth)

                return m

        self.assert_re("not defined", Circuit())


WIDTH = 8


class Quadruple(Elaboratable):
    def __init__(self):
        layout = data_layout(WIDTH)
        self.id = Method(i=layout, o=layout)
        self.double = Method(i=layout, o=layout)
        self.quadruple = Method(i=layout, o=layout)

    def elaborate(self, platform):
        m = TModule()

        @def_method(m, self.id)
        def _(arg):
            return arg

        @def_method(m, self.double)
        def _(arg):
            return {"data": self.id(m, arg).data * 2}

        @def_method(m, self.quadruple)
        def _(arg):
            return {"data": self.double(m, arg).data * 2}

        return m


class QuadrupleCircuit(Elaboratable):
    def __init__(self, quadruple):
        self.quadruple = quadruple

    def elaborate(self, platform):
        m = TModule()

        m.submodules.quadruple = self.quadruple
        m.submodules.tb = self.tb = TestbenchIO(AdapterTrans(self.quadruple.quadruple))

        return m


class Quadruple2(Elaboratable):
    def __init__(self):
        layout = data_layout(WIDTH)
        self.quadruple = Method(i=layout, o=layout)

    def elaborate(self, platform):
        m = TModule()

        m.submodules.sub = Quadruple()

        @def_method(m, self.quadruple)
        def _(arg):
            return {"data": 2 * m.submodules.sub.double(m, arg).data}

        return m


class TestQuadrupleCircuits(TestCaseWithSimulator):
    @parameterized.expand([(Quadruple,), (Quadruple2,)])
    def test(self, quadruple):
        circ = QuadrupleCircuit(quadruple())

        def process():
            for n in range(1 << (WIDTH - 2)):
                out = yield from circ.tb.call(data=n)
                self.assertEqual(out["data"], n * 4)

        with self.run_simulation(circ) as sim:
            sim.add_sync_process(process)


class ConditionalCallCircuit(Elaboratable):
    def elaborate(self, platform):
        m = TModule()

        meth = Method(i=data_layout(1))

        m.submodules.tb = self.tb = TestbenchIO(AdapterTrans(meth))
        m.submodules.out = self.out = TestbenchIO(Adapter())

        @def_method(m, meth)
        def _(arg):
            with m.If(arg):
                self.out.adapter.iface(m)

        return m


class ConditionalMethodCircuit1(Elaboratable):
    def elaborate(self, platform):
        m = TModule()

        meth = Method()

        self.ready = Signal()
        m.submodules.tb = self.tb = TestbenchIO(AdapterTrans(meth))

        @def_method(m, meth, ready=self.ready)
        def _(arg):
            pass

        return m


class ConditionalMethodCircuit2(Elaboratable):
    def elaborate(self, platform):
        m = TModule()

        meth = Method()

        self.ready = Signal()
        m.submodules.tb = self.tb = TestbenchIO(AdapterTrans(meth))

        with m.If(self.ready):

            @def_method(m, meth)
            def _(arg):
                pass

        return m


class ConditionalTransactionCircuit1(Elaboratable):
    def elaborate(self, platform):
        m = TModule()

        self.ready = Signal()
        m.submodules.tb = self.tb = TestbenchIO(Adapter())

        with Transaction().body(m, request=self.ready):
            self.tb.adapter.iface(m)

        return m


class ConditionalTransactionCircuit2(Elaboratable):
    def elaborate(self, platform):
        m = TModule()

        self.ready = Signal()
        m.submodules.tb = self.tb = TestbenchIO(Adapter())

        with m.If(self.ready):
            with Transaction().body(m):
                self.tb.adapter.iface(m)

        return m


class TestConditionals(TestCaseWithSimulator):
    def test_conditional_call(self):
        circ = ConditionalCallCircuit()

        def process():
            yield from circ.out.disable()
            yield from circ.tb.call_init(data=0)
            yield Settle()
            self.assertFalse((yield from circ.out.done()))
            self.assertFalse((yield from circ.tb.done()))

            yield from circ.out.enable()
            yield Settle()
            self.assertFalse((yield from circ.out.done()))
            self.assertTrue((yield from circ.tb.done()))

            yield from circ.tb.call_init(data=1)
            yield Settle()
            self.assertTrue((yield from circ.out.done()))
            self.assertTrue((yield from circ.tb.done()))

            # the argument is still 1 but the method is not called
            yield from circ.tb.disable()
            yield Settle()
            self.assertFalse((yield from circ.out.done()))
            self.assertFalse((yield from circ.tb.done()))

        with self.run_simulation(circ) as sim:
            sim.add_sync_process(process)

    @parameterized.expand(
        [
            (ConditionalMethodCircuit1,),
            (ConditionalMethodCircuit2,),
            (ConditionalTransactionCircuit1,),
            (ConditionalTransactionCircuit2,),
        ]
    )
    def test_conditional(self, elaboratable):
        circ = elaboratable()

        def process():
            yield from circ.tb.enable()
            yield circ.ready.eq(0)
            yield Settle()
            self.assertFalse((yield from circ.tb.done()))

            yield circ.ready.eq(1)
            yield Settle()
            self.assertTrue((yield from circ.tb.done()))

        with self.run_simulation(circ) as sim:
            sim.add_sync_process(process)


class NonexclusiveMethodCircuit(Elaboratable):
    def elaborate(self, platform):
        m = TModule()

        self.ready = Signal()
        self.running = Signal()
        self.data = Signal(WIDTH)

        method = Method(o=data_layout(WIDTH), nonexclusive=True)

        @def_method(m, method, self.ready)
        def _():
            m.d.comb += self.running.eq(1)
            return {"data": self.data}

        m.submodules.t1 = self.t1 = TestbenchIO(AdapterTrans(method))
        m.submodules.t2 = self.t2 = TestbenchIO(AdapterTrans(method))

        return m


class TestNonexclusiveMethod(TestCaseWithSimulator):
    def test_nonexclusive_method(self):
        circ = NonexclusiveMethodCircuit()

        def process():
            for x in range(8):
                t1en = bool(x & 1)
                t2en = bool(x & 2)
                mrdy = bool(x & 4)

                if t1en:
                    yield from circ.t1.enable()
                else:
                    yield from circ.t1.disable()

                if t2en:
                    yield from circ.t2.enable()
                else:
                    yield from circ.t2.disable()

                if mrdy:
                    yield circ.ready.eq(1)
                else:
                    yield circ.ready.eq(0)

                yield circ.data.eq(x)
                yield Settle()

                self.assertEqual(bool((yield circ.running)), (t1en or t2en) and mrdy)
                self.assertEqual(bool((yield from circ.t1.done())), t1en and mrdy)
                self.assertEqual(bool((yield from circ.t2.done())), t2en and mrdy)

                if t1en and mrdy:
                    self.assertEqual((yield from circ.t1.get_outputs()), {"data": x})

                if t2en and mrdy:
                    self.assertEqual((yield from circ.t2.get_outputs()), {"data": x})

        with self.run_simulation(circ) as sim:
            sim.add_sync_process(process)


class DataDependentConditionalCircuit(Elaboratable):
    def __init__(self, n=2, ready_function=lambda arg: arg.data != 3):
        self.method = Method(i=data_layout(n))
        self.ready_function = ready_function

        self.in_t1 = Signal(from_method_layout(data_layout(n)))
        self.in_t2 = Signal(from_method_layout(data_layout(n)))
        self.ready = Signal()
        self.req_t1 = Signal()
        self.req_t2 = Signal()

        self.out_m = Signal()
        self.out_t1 = Signal()
        self.out_t2 = Signal()

    def elaborate(self, platform):
        m = TModule()

        @def_method(m, self.method, self.ready, validate_arguments=self.ready_function)
        def _(data):
            m.d.comb += self.out_m.eq(1)

        with Transaction().body(m, request=self.req_t1):
            m.d.comb += self.out_t1.eq(1)
            self.method(m, self.in_t1)

        with Transaction().body(m, request=self.req_t2):
            m.d.comb += self.out_t2.eq(1)
            self.method(m, self.in_t2)

        return m


class TestDataDependentConditionalMethod(TestCaseWithSimulator):
    def setUp(self):
        self.test_number = 200
        self.bad_number = 3
        self.n = 2

    def base_random(self, f):
        random.seed(14)
        self.circ = DataDependentConditionalCircuit(n=self.n, ready_function=f)

        def process():
            for _ in range(self.test_number):
                in1 = random.randrange(0, 2**self.n)
                in2 = random.randrange(0, 2**self.n)
                m_ready = random.randrange(2)
                req_t1 = random.randrange(2)
                req_t2 = random.randrange(2)

                yield self.circ.in_t1.eq(in1)
                yield self.circ.in_t2.eq(in2)
                yield self.circ.req_t1.eq(req_t1)
                yield self.circ.req_t2.eq(req_t2)
                yield self.circ.ready.eq(m_ready)
                yield Settle()

                out_m = yield self.circ.out_m
                out_t1 = yield self.circ.out_t1
                out_t2 = yield self.circ.out_t2

                if not m_ready or (not req_t1 or in1 == self.bad_number) and (not req_t2 or in2 == self.bad_number):
                    self.assertEqual(out_m, 0)
                    self.assertEqual(out_t1, 0)
                    self.assertEqual(out_t2, 0)
                    continue
                # Here method global ready signal is high and we requested one of the transactions
                # we also know that one of the transactions request correct input data

                self.assertEqual(out_m, 1)
                self.assertEqual(out_t1 ^ out_t2, 1)
                # inX == self.bad_number implies out_tX==0
                self.assertTrue(in1 != self.bad_number or not out_t1)
                self.assertTrue(in2 != self.bad_number or not out_t2)

                yield

        with self.run_simulation(self.circ, 100) as sim:
            sim.add_sync_process(process)

    def test_random_arg(self):
        self.base_random(lambda arg: arg.data != self.bad_number)

    def test_random_kwarg(self):
        self.base_random(lambda data: data != self.bad_number)
