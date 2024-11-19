from collections.abc import Callable, Sequence
import pytest
import random
from amaranth import *
from amaranth.sim import *

from transactron.testing import TestCaseWithSimulator, TestbenchIO, data_layout

from transactron import *
from transactron.testing.infrastructure import SimpleTestCircuit
from transactron.utils import MethodStruct
from transactron.lib import *

from parameterized import parameterized

from unittest import TestCase

from transactron.utils.assign import AssignArg


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

        with pytest.raises(KeyError):
            self.do_test_definition(definition)

    def test_fields_invalid2(self):
        def definition(arg):
            return {"foo1": Signal(3)}

        with pytest.raises(KeyError):
            self.do_test_definition(definition)

    def test_fields_invalid3(self):
        def definition(arg):
            return {"foo1": {"baz1": Signal(), "baz2": Signal()}, "foo2": {"bar1": Signal(4), "bar2": Signal(6)}}

        with pytest.raises(TypeError):
            self.do_test_definition(definition)

    def test_fields_invalid4(self):
        def definition(arg: Value):
            return arg

        with pytest.raises(TypeError):
            self.do_test_definition(definition)

    def test_fields_invalid5(self):
        def definition(foo):
            return foo

        with pytest.raises(TypeError):
            self.do_test_definition(definition)

    def test_fields_invalid6(self):
        def definition(foo1):
            return {"foo1": foo1, "foo2": {"bar1": Signal(4), "bar2": Signal(6)}}

        with pytest.raises(TypeError):
            self.do_test_definition(definition)


class TestDefMethods(TestCaseWithSimulator):
    class CircuitTestModule(Elaboratable):
        def __init__(self, method_definition):
            self.methods = [
                Method(
                    i=[("foo", 3)],
                    o=[("foo", 3)],
                )
                for _ in range(4)
            ]

            self.method_definition = method_definition

        def elaborate(self, platform):
            m = TModule()
            m._MustUse__silence = True  # type: ignore

            def_methods(m, self.methods)(self.method_definition)

            return m

    def test_basic_methods(self):
        def definition(idx: int, foo: Value):
            return {"foo": foo + idx}

        circuit = SimpleTestCircuit(TestDefMethods.CircuitTestModule(definition))

        async def test_process(sim):
            for k, method in enumerate(circuit.methods):
                val = random.randrange(0, 2**3)
                ret = await method.call(sim, foo=val)
                assert ret["foo"] == (val + k) % 2**3

        with self.run_simulation(circuit) as sim:
            sim.add_testbench(test_process)


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
        with pytest.raises(RuntimeError, match=msg):
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

        async def process(sim):
            for n in range(1 << (WIDTH - 2)):
                out = await circ.tb.call(sim, data=n)
                assert out["data"] == n * 4

        with self.run_simulation(circ) as sim:
            sim.add_testbench(process)


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

        async def process(sim):
            circ.out.disable(sim)
            circ.tb.call_init(sim, data=0)
            *_, out_done, tb_done = await sim.tick().sample(circ.out.adapter.done, circ.tb.adapter.done)
            assert not out_done and not tb_done

            circ.out.enable(sim)
            *_, out_done, tb_done = await sim.tick().sample(circ.out.adapter.done, circ.tb.adapter.done)
            assert not out_done and tb_done

            circ.tb.call_init(sim, data=1)
            *_, out_done, tb_done = await sim.tick().sample(circ.out.adapter.done, circ.tb.adapter.done)
            assert out_done and tb_done

            # the argument is still 1 but the method is not called
            circ.tb.disable(sim)
            *_, out_done, tb_done = await sim.tick().sample(circ.out.adapter.done, circ.tb.adapter.done)
            assert not out_done and not tb_done

        with self.run_simulation(circ) as sim:
            sim.add_testbench(process)

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

        async def process(sim):
            circ.tb.enable(sim)
            sim.set(circ.ready, 0)
            *_, tb_done = await sim.tick().sample(circ.tb.adapter.done)
            assert not tb_done

            sim.set(circ.ready, 1)
            *_, tb_done = await sim.tick().sample(circ.tb.adapter.done)
            assert tb_done

        with self.run_simulation(circ) as sim:
            sim.add_testbench(process)


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

        async def process(sim):
            for x in range(8):
                t1en = bool(x & 1)
                t2en = bool(x & 2)
                mrdy = bool(x & 4)

                circ.t1.set_enable(sim, t1en)
                circ.t2.set_enable(sim, t2en)
                sim.set(circ.ready, int(mrdy))
                sim.set(circ.data, x)

                *_, running, t1_done, t2_done, t1_outputs, t2_outputs = await sim.delay(1e-9).sample(
                    circ.running, circ.t1.done, circ.t2.done, circ.t1.outputs, circ.t2.outputs
                )

                assert bool(running) == ((t1en or t2en) and mrdy)
                assert bool(t1_done) == (t1en and mrdy)
                assert bool(t2_done) == (t2en and mrdy)

                if t1en and mrdy:
                    assert t1_outputs["data"] == x

                if t2en and mrdy:
                    assert t2_outputs["data"] == x

        with self.run_simulation(circ) as sim:
            sim.add_testbench(process)


class TwoNonexclusiveConflictCircuit(Elaboratable):
    def __init__(self, two_nonexclusive: bool):
        self.two_nonexclusive = two_nonexclusive

    def elaborate(self, platform):
        m = TModule()

        self.running1 = Signal()
        self.running2 = Signal()

        method1 = Method(o=data_layout(WIDTH), nonexclusive=True)
        method2 = Method(o=data_layout(WIDTH), nonexclusive=self.two_nonexclusive)
        method_in = Method(o=data_layout(WIDTH))

        @def_method(m, method_in)
        def _():
            return {"data": 0}

        @def_method(m, method1)
        def _():
            m.d.comb += self.running1.eq(1)
            return method_in(m)

        @def_method(m, method2)
        def _():
            m.d.comb += self.running2.eq(1)
            return method_in(m)

        m.submodules.t1 = self.t1 = TestbenchIO(AdapterTrans(method1))
        m.submodules.t2 = self.t2 = TestbenchIO(AdapterTrans(method2))

        return m


class TestConflicting(TestCaseWithSimulator):
    @pytest.mark.parametrize(
        "test_circuit", [lambda: TwoNonexclusiveConflictCircuit(False), lambda: TwoNonexclusiveConflictCircuit(True)]
    )
    def test_conflicting(self, test_circuit: Callable[[], TwoNonexclusiveConflictCircuit]):
        circ = test_circuit()

        async def process(sim):
            circ.t1.enable(sim)
            circ.t2.enable(sim)
            *_, running1, running2 = await sim.delay(1e-9).sample(circ.running1, circ.running2)

            assert not running1 or not running2

        with self.run_simulation(circ) as sim:
            sim.add_testbench(process)


class CustomCombinerMethodCircuit(Elaboratable):
    def elaborate(self, platform):
        m = TModule()

        self.ready = Signal()
        self.running = Signal()

        def combiner(m: Module, args: Sequence[MethodStruct], runs: Value) -> AssignArg:
            result = C(0)
            for i, v in enumerate(args):
                result = result ^ Mux(runs[i], v.data, 0)
            return {"data": result}

        method = Method(i=data_layout(WIDTH), o=data_layout(WIDTH), nonexclusive=True, combiner=combiner)

        @def_method(m, method, self.ready)
        def _(data: Value):
            m.d.comb += self.running.eq(1)
            return {"data": data}

        m.submodules.t1 = self.t1 = TestbenchIO(AdapterTrans(method))
        m.submodules.t2 = self.t2 = TestbenchIO(AdapterTrans(method))

        return m


class TestCustomCombinerMethod(TestCaseWithSimulator):
    def test_custom_combiner_method(self):
        circ = CustomCombinerMethodCircuit()

        async def process(sim):
            for x in range(8):
                t1en = bool(x & 1)
                t2en = bool(x & 2)
                mrdy = bool(x & 4)

                val1 = random.randrange(0, 2**WIDTH)
                val2 = random.randrange(0, 2**WIDTH)
                val1e = val1 if t1en else 0
                val2e = val2 if t2en else 0

                circ.t1.call_init(sim, data=val1)
                circ.t2.call_init(sim, data=val2)

                circ.t1.set_enable(sim, t1en)
                circ.t2.set_enable(sim, t2en)

                sim.set(circ.ready, int(mrdy))

                *_, running, t1_done, t2_done, t1_outputs, t2_outputs = await sim.delay(1e-9).sample(
                    circ.running, circ.t1.done, circ.t2.done, circ.t1.outputs, circ.t2.outputs
                )

                assert bool(running) == ((t1en or t2en) and mrdy)
                assert bool(t1_done) == (t1en and mrdy)
                assert bool(t2_done) == (t2en and mrdy)

                if t1en and mrdy:
                    assert t1_outputs["data"] == val1e ^ val2e

                if t2en and mrdy:
                    assert t2_outputs["data"] == val1e ^ val2e

        with self.run_simulation(circ) as sim:
            sim.add_testbench(process)


class DataDependentConditionalCircuit(Elaboratable):
    def __init__(self, n=2, ready_function=lambda arg: arg.data != 3):
        self.method = Method(i=data_layout(n))
        self.ready_function = ready_function

        self.in_t1 = Signal(n)
        self.in_t2 = Signal(n)
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
            self.method(m, data=self.in_t1)

        with Transaction().body(m, request=self.req_t2):
            m.d.comb += self.out_t2.eq(1)
            self.method(m, data=self.in_t2)

        return m


class TestDataDependentConditionalMethod(TestCaseWithSimulator):
    def setup_method(self):
        self.test_number = 200
        self.bad_number = 3
        self.n = 2

    def base_random(self, f):
        random.seed(14)
        self.circ = DataDependentConditionalCircuit(n=self.n, ready_function=f)

        async def process(sim):
            for _ in range(self.test_number):
                in1 = random.randrange(0, 2**self.n)
                in2 = random.randrange(0, 2**self.n)
                m_ready = random.randrange(2)
                req_t1 = random.randrange(2)
                req_t2 = random.randrange(2)

                sim.set(self.circ.in_t1, in1)
                sim.set(self.circ.in_t2, in2)
                sim.set(self.circ.req_t1, req_t1)
                sim.set(self.circ.req_t2, req_t2)
                sim.set(self.circ.ready, m_ready)

                *_, out_m, out_t1, out_t2 = await sim.delay(1e-9).sample(
                    self.circ.out_m, self.circ.out_t1, self.circ.out_t2
                )

                if not m_ready or (not req_t1 or in1 == self.bad_number) and (not req_t2 or in2 == self.bad_number):
                    assert out_m == 0
                    assert out_t1 == 0
                    assert out_t2 == 0
                    continue
                # Here method global ready signal is high and we requested one of the transactions
                # we also know that one of the transactions request correct input data

                assert out_m == 1
                assert out_t1 ^ out_t2 == 1
                # inX == self.bad_number implies out_tX==0
                assert in1 != self.bad_number or not out_t1
                assert in2 != self.bad_number or not out_t2

                await sim.tick()

        with self.run_simulation(self.circ, 100) as sim:
            sim.add_testbench(process)

    def test_random_arg(self):
        self.base_random(lambda arg: arg.data != self.bad_number)

    def test_random_kwarg(self):
        self.base_random(lambda data: data != self.bad_number)
