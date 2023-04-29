import random
from operator import and_
from functools import reduce
from typing import TypeAlias
from amaranth.sim import Settle
from parameterized import parameterized

from amaranth import *
from coreblocks.transactions import *
from coreblocks.transactions.core import RecordDict
from coreblocks.transactions.lib import *
from coreblocks.utils._typing import LayoutLike
from ..common import (
    SimpleTestCircuit,
    TestCaseWithSimulator,
    TestbenchIO,
    data_layout,
    def_method_mock,
)


FIFO_Like: TypeAlias = FIFO | Forwarder


class TestFifoBase(TestCaseWithSimulator):
    def do_test_fifo(
        self, fifo_class: type[FIFO_Like], writer_rand: int = 0, reader_rand: int = 0, fifo_kwargs: dict = {}
    ):
        iosize = 8

        m = SimpleTestCircuit(fifo_class(data_layout(iosize), **fifo_kwargs))

        random.seed(1337)

        def random_wait(rand: int):
            yield from self.tick(random.randint(0, rand))

        def writer():
            for i in range(2**iosize):
                yield from m.write.call(data=i)
                yield from random_wait(writer_rand)

        def reader():
            for i in range(2**iosize):
                self.assertEqual((yield from m.read.call()), {"data": i})
                yield from random_wait(reader_rand)

        with self.run_simulation(m) as sim:
            sim.add_sync_process(reader)
            sim.add_sync_process(writer)


class TestFIFO(TestFifoBase):
    @parameterized.expand([(0, 0), (2, 0), (0, 2), (1, 1)])
    def test_fifo(self, writer_rand, reader_rand):
        self.do_test_fifo(FIFO, writer_rand=writer_rand, reader_rand=reader_rand, fifo_kwargs=dict(depth=4))


class TestForwarder(TestFifoBase):
    @parameterized.expand([(0, 0), (2, 0), (0, 2), (1, 1)])
    def test_fifo(self, writer_rand, reader_rand):
        self.do_test_fifo(Forwarder, writer_rand=writer_rand, reader_rand=reader_rand)

    def test_forwarding(self):
        iosize = 8

        m = SimpleTestCircuit(Forwarder(data_layout(iosize)))

        def forward_check(x):
            yield from m.read.call_init()
            yield from m.write.call_init(data=x)
            yield Settle()
            self.assertEqual((yield from m.read.call_result()), {"data": x})
            self.assertIsNotNone((yield from m.write.call_result()))
            yield

        def process():
            # test forwarding behavior
            for x in range(4):
                yield from forward_check(x)

            # load the overflow buffer
            yield from m.read.disable()
            yield from m.write.call_init(data=42)
            yield Settle()
            self.assertIsNotNone((yield from m.write.call_result()))
            yield

            # writes are not possible now
            yield from m.write.call_init(data=84)
            yield Settle()
            self.assertIsNone((yield from m.write.call_result()))
            yield

            # read from the overflow buffer, writes still blocked
            yield from m.read.enable()
            yield from m.write.call_init(data=111)
            yield Settle()
            self.assertEqual((yield from m.read.call_result()), {"data": 42})
            self.assertIsNone((yield from m.write.call_result()))
            yield

            # forwarding now works again
            for x in range(4):
                yield from forward_check(x)

        with self.run_simulation(m) as sim:
            sim.add_sync_process(process)


class ManyToOneConnectTransTestCircuit(Elaboratable):
    def __init__(self, count: int, lay: LayoutLike):
        self.count = count
        self.lay = lay
        self.inputs = []

    def elaborate(self, platform):
        m = Module()

        # dummy signal
        s = Signal()
        m.d.sync += s.eq(1)

        get_results = []
        for i in range(self.count):
            input = TestbenchIO(Adapter(o=self.lay))
            get_results.append(input.adapter.iface)
            m.submodules[f"input_{i}"] = input
            self.inputs.append(input)

        # Create ManyToOneConnectTrans, which will serialize results from different inputs
        output = TestbenchIO(Adapter(i=self.lay))
        m.submodules.output = output
        self.output = output
        m.submodules.fu_arbitration = ManyToOneConnectTrans(
            get_results=get_results, put_result=output.adapter.iface
        )

        return m


class TestManyToOneConnectTrans(TestCaseWithSimulator):
    def initialize(self):
        f1_size = 14
        f2_size = 3
        self.lay = [("field1", f1_size), ("field2", f2_size)]

        self.m = ManyToOneConnectTransTestCircuit(self.count, self.lay)
        random.seed(14)

        self.inputs = []
        # Create list with info if we processed all data from inputs
        self.producer_end = [False for i in range(self.count)]
        self.expected_output = {}

        # Prepare random results for inputs
        for i in range(self.count):
            data = []
            input_size = random.randint(20, 30)
            for j in range(input_size):
                t = (
                    random.randint(0, 2**f1_size),
                    random.randint(0, 2**f2_size),
                )
                data.append(t)
                if t in self.expected_output:
                    self.expected_output[t] += 1
                else:
                    self.expected_output[t] = 1
            self.inputs.append(data)

    def random_wait(self):
        for i in range(random.randint(0, 3)):
            yield

    def generate_producer(self, i: int):
        """
        This is an helper function, which generates a producer process,
        which will simulate an FU. Producer will insert in random intervals new
        results to its output FIFO. This records will be next serialized by FUArbiter.
        """

        def producer():
            inputs = self.inputs[i]
            for field1, field2 in inputs:
                io: TestbenchIO = self.m.inputs[i]
                yield from io.call_init(field1=field1, field2=field2)
                yield from self.random_wait()
            self.producer_end[i] = True

        return producer

    def consumer(self):
        while reduce(and_, self.producer_end, True):
            result = yield from self.m.output.call_do()

            self.assertIsNotNone(result)

            # this is needed to make the typechecker happy
            if result is None:
                continue

            t = (result["field1"], result["field2"])
            self.assertIn(t, self.expected_output)
            if self.expected_output[t] == 1:
                del self.expected_output[t]
            else:
                self.expected_output[t] -= 1
            yield from self.random_wait()

    def test_one_out(self):
        self.count = 1
        self.initialize()
        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.consumer)
            for i in range(self.count):
                sim.add_sync_process(self.generate_producer(i))

    def test_many_out(self):
        self.count = 4
        self.initialize()
        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.consumer)
            for i in range(self.count):
                sim.add_sync_process(self.generate_producer(i))


class MethodTransformerTestCircuit(Elaboratable):
    def __init__(self, iosize: int, use_methods: bool, use_dicts: bool):
        self.iosize = iosize
        self.use_methods = use_methods
        self.use_dicts = use_dicts

    def elaborate(self, platform):
        m = Module()

        # dummy signal
        s = Signal()
        m.d.sync += s.eq(1)

        layout = data_layout(self.iosize)

        def itransform_rec(m: Module, v: Record) -> Record:
            s = Record.like(v)
            m.d.comb += s.data.eq(v.data + 1)
            return s

        def otransform_rec(m: Module, v: Record) -> Record:
            s = Record.like(v)
            m.d.comb += s.data.eq(v.data - 1)
            return s

        def itransform_dict(_, v: Record) -> RecordDict:
            return {"data": v.data + 1}

        def otransform_dict(_, v: Record) -> RecordDict:
            return {"data": v.data - 1}

        if self.use_dicts:
            itransform = itransform_dict
            otransform = otransform_dict
        else:
            itransform = itransform_rec
            otransform = otransform_rec

        m.submodules.target = self.target = TestbenchIO(Adapter(i=layout, o=layout))

        if self.use_methods:
            imeth = Method(i=layout, o=layout)
            ometh = Method(i=layout, o=layout)

            @def_method(m, imeth)
            def _(arg: Record):
                return itransform(m, arg)

            @def_method(m, ometh)
            def _(arg: Record):
                return otransform(m, arg)

            trans = MethodTransformer(
                self.target.adapter.iface, i_transform=(layout, imeth), o_transform=(layout, ometh)
            )
        else:
            trans = MethodTransformer(
                self.target.adapter.iface,
                i_transform=(layout, itransform),
                o_transform=(layout, otransform),
            )

        m.submodules.trans = trans

        m.submodules.source = self.source = TestbenchIO(AdapterTrans(trans.method))

        return m


class TestMethodTransformer(TestCaseWithSimulator):
    m: MethodTransformerTestCircuit

    def source(self):
        for i in range(2**self.m.iosize):
            v = yield from self.m.source.call(data=i)
            i1 = (i + 1) & ((1 << self.m.iosize) - 1)
            self.assertEqual(v["data"], (((i1 << 1) | (i1 >> (self.m.iosize - 1))) - 1) & ((1 << self.m.iosize) - 1))

    @def_method_mock(lambda self: self.m.target)
    def target(self, data):
        return {"data": (data << 1) | (data >> (self.m.iosize - 1))}

    def test_method_transformer(self):
        self.m = MethodTransformerTestCircuit(4, False, False)
        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.source)
            sim.add_sync_process(self.target)

    def test_method_transformer_dicts(self):
        self.m = MethodTransformerTestCircuit(4, False, True)
        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.source)
            sim.add_sync_process(self.target)

    def test_method_transformer_with_methods(self):
        self.m = MethodTransformerTestCircuit(4, True, True)
        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.source)
            sim.add_sync_process(self.target)


class MethodFilterTestCircuit(Elaboratable):
    def __init__(self, iosize: int, use_methods: bool):
        self.iosize = iosize
        self.use_methods = use_methods

    def elaborate(self, platform):
        m = Module()

        # dummy signal
        s = Signal()
        m.d.sync += s.eq(1)

        layout = data_layout(self.iosize)

        m.submodules.target = self.target = TestbenchIO(Adapter(i=layout, o=layout))

        def condition(_, v):
            return v[0]

        if self.use_methods:
            cmeth = Method(i=layout, o=data_layout(1))

            @def_method(m, cmeth)
            def _(arg: Record):
                return condition(m, arg)

            filt = MethodFilter(self.target.adapter.iface, cmeth)
        else:
            filt = MethodFilter(self.target.adapter.iface, condition)

        m.submodules.filt = filt

        m.submodules.source = self.source = TestbenchIO(AdapterTrans(filt.method))

        return m


class TestMethodFilter(TestCaseWithSimulator):
    m: MethodFilterTestCircuit

    def source(self):
        for i in range(2**self.m.iosize):
            v = yield from self.m.source.call(data=i)
            if i & 1:
                self.assertEqual(v["data"], (i + 1) & ((1 << self.m.iosize) - 1))
            else:
                self.assertEqual(v["data"], 0)

    @def_method_mock(lambda self: self.m.target)
    def target(self, data):
        return {"data": data + 1}

    def test_method_filter(self):
        self.m = MethodFilterTestCircuit(4, False)
        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.source)
            sim.add_sync_process(self.target)

    def test_method_filter_with_methods(self):
        self.m = MethodFilterTestCircuit(4, True)
        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.source)
            sim.add_sync_process(self.target)


class MethodProductTestCircuit(Elaboratable):
    def __init__(self, iosize: int, targets: int, add_combiner: bool):
        self.iosize = iosize
        self.targets = targets
        self.add_combiner = add_combiner
        self.target: list[TestbenchIO] = []

    def elaborate(self, platform):
        m = Module()

        # dummy signal
        s = Signal()
        m.d.sync += s.eq(1)

        layout = data_layout(self.iosize)

        methods = []

        for k in range(self.targets):
            tgt = TestbenchIO(Adapter(i=layout, o=layout))
            methods.append(tgt.adapter.iface)
            self.target.append(tgt)
            m.submodules += tgt

        combiner = None
        if self.add_combiner:
            combiner = (layout, lambda _, vs: {"data": sum(vs)})

        m.submodules.product = product = MethodProduct(methods, combiner)

        m.submodules.method = self.method = TestbenchIO(AdapterTrans(product.method))

        return m


class TestMethodProduct(TestCaseWithSimulator):
    @parameterized.expand([(1, False), (2, False), (5, True)])
    def test_method_product(self, targets: int, add_combiner: bool):
        random.seed(14)

        iosize = 8
        m = MethodProductTestCircuit(iosize, targets, add_combiner)

        method_en = [False] * targets

        def target_process(k: int):
            @def_method_mock(lambda: m.target[k], enable=lambda: method_en[k])
            def process(data):
                return {"data": data + k}

            return process

        def method_process():
            # if any of the target methods is not enabled, call does not succeed
            for i in range(2**targets - 1):
                for k in range(targets):
                    method_en[k] = bool(i & (1 << k))

                yield
                self.assertIsNone((yield from m.method.call_try(data=0)))

            # otherwise, the call succeeds
            for k in range(targets):
                method_en[k] = True
            yield

            data = random.randint(0, (1 << iosize) - 1)
            val = (yield from m.method.call(data=data))["data"]
            if add_combiner:
                self.assertEqual(val, (targets * data + (targets - 1) * targets // 2) & ((1 << iosize) - 1))
            else:
                self.assertEqual(val, data)

        with self.run_simulation(m) as sim:
            sim.add_sync_process(method_process)
            for k in range(targets):
                sim.add_sync_process(target_process(k))
