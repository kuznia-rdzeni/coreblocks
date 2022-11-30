import random
from operator import and_
from functools import reduce

from amaranth import *
from amaranth.sim.core import Passive, Settle
from coreblocks.transactions import *
from coreblocks.transactions.core import RecordDict
from coreblocks.transactions.lib import Adapter, AdapterTrans, ManyToOneConnectTrans, MethodFilter, MethodTransformer
from coreblocks.utils._typing import LayoutLike
from ..common import TestCaseWithSimulator, TestbenchIO


class ManyToOneConnectTransTestCircuit(Elaboratable):
    def __init__(self, count: int, lay: LayoutLike):
        self.count = count
        self.lay = lay

    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        # dummy signal
        s = Signal()
        m.d.sync += s.eq(1)

        with tm.transactionContext():
            get_results = []
            for i in range(self.count):
                input = TestbenchIO(Adapter(i=self.lay, o=self.lay))
                get_results.append(input.adapter.iface)
                setattr(m.submodules, f"input_{i}", input)
                setattr(self, f"input_{i}", input)

            # Create ManyToOneConnectTrans, which will serialize results from different inputs
            output = TestbenchIO(Adapter(i=self.lay))
            m.submodules.output = output
            self.output = output
            m.submodules.fu_arbitration = ManyToOneConnectTrans(
                get_results=get_results, put_result=output.adapter.iface
            )

        return tm


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
                input_dict = {"field1": field1, "field2": field2}
                yield from getattr(self.m, f"input_{i}").call_init(input_dict)
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
        with self.runSimulation(self.m) as sim:
            sim.add_sync_process(self.consumer)
            for i in range(self.count):
                sim.add_sync_process(self.generate_producer(i))

    def test_many_out(self):
        self.count = 4
        self.initialize()
        with self.runSimulation(self.m) as sim:
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
        tm = TransactionModule(m)

        # dummy signal
        s = Signal()
        m.d.sync += s.eq(1)

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

        with tm.transactionContext():
            m.submodules.target = self.target = TestbenchIO(Adapter(i=self.iosize, o=self.iosize))

            if self.use_methods:
                imeth = Method(i=self.iosize, o=self.iosize)
                ometh = Method(i=self.iosize, o=self.iosize)

                @def_method(m, imeth)
                def _(v: Record):
                    return itransform(m, v)

                @def_method(m, ometh)
                def _(v: Record):
                    return otransform(m, v)

                trans = MethodTransformer(
                    self.target.adapter.iface, i_transform=(self.iosize, imeth), o_transform=(self.iosize, ometh)
                )
            else:

                trans = MethodTransformer(
                    self.target.adapter.iface,
                    i_transform=(self.iosize, itransform),
                    o_transform=(self.iosize, otransform),
                )

            m.submodules.trans = trans

            m.submodules.source = self.source = TestbenchIO(AdapterTrans(trans.method))

        return tm


class TestMethodTransformer(TestCaseWithSimulator):
    m: MethodTransformerTestCircuit

    def source(self):
        for i in range(2**self.m.iosize):
            v = yield from self.m.source.call({"data": i})
            i1 = (i + 1) & ((1 << self.m.iosize) - 1)
            self.assertEqual(v["data"], (((i1 << 1) | (i1 >> (self.m.iosize - 1))) - 1) & ((1 << self.m.iosize) - 1))

    def target(self):
        yield Passive()
        yield from self.m.target.enable()

        while True:
            yield Settle()
            v = yield from self.m.target.call_result()
            if v is not None:
                yield from self.m.target.call_init({"data": (v["data"] << 1) | (v["data"] >> (self.m.iosize - 1))})
            yield

    def test_method_transformer(self):
        self.m = MethodTransformerTestCircuit(4, False, False)
        with self.runSimulation(self.m) as sim:
            sim.add_sync_process(self.source)
            sim.add_sync_process(self.target)

    def test_method_transformer_dicts(self):
        self.m = MethodTransformerTestCircuit(4, False, True)
        with self.runSimulation(self.m) as sim:
            sim.add_sync_process(self.source)
            sim.add_sync_process(self.target)

    def test_method_transformer_with_methods(self):
        self.m = MethodTransformerTestCircuit(4, True, True)
        with self.runSimulation(self.m) as sim:
            sim.add_sync_process(self.source)
            sim.add_sync_process(self.target)


class MethodFilterTestCircuit(Elaboratable):
    def __init__(self, iosize: int, use_methods: bool):
        self.iosize = iosize
        self.use_methods = use_methods

    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        # dummy signal
        s = Signal()
        m.d.sync += s.eq(1)

        with tm.transactionContext():
            m.submodules.target = self.target = TestbenchIO(Adapter(i=self.iosize, o=self.iosize))

            def condition(_, v):
                return v[0]

            if self.use_methods:
                cmeth = Method(i=self.iosize, o=1)

                @def_method(m, cmeth)
                def _(v):
                    return condition(m, v)

                filt = MethodFilter(self.target.adapter.iface, cmeth)
            else:
                filt = MethodFilter(self.target.adapter.iface, condition)

            m.submodules.filt = filt

            m.submodules.source = self.source = TestbenchIO(AdapterTrans(filt.method))

        return tm


class TestMethodFilter(TestCaseWithSimulator):
    m: MethodFilterTestCircuit

    def source(self):
        for i in range(2**self.m.iosize):
            v = yield from self.m.source.call({"data": i})
            if i & 1:
                self.assertEqual(v["data"], (i + 1) & ((1 << self.m.iosize) - 1))
            else:
                self.assertEqual(v["data"], 0)

    def target(self):
        yield Passive()
        yield from self.m.target.enable()

        while True:
            yield Settle()
            v = yield from self.m.target.call_result()
            if v is not None:
                yield from self.m.target.call_init({"data": v["data"] + 1})
            yield

    def test_method_filter(self):
        self.m = MethodFilterTestCircuit(4, False)
        with self.runSimulation(self.m) as sim:
            sim.add_sync_process(self.source)
            sim.add_sync_process(self.target)

    def test_method_filter_with_methods(self):
        self.m = MethodFilterTestCircuit(4, True)
        with self.runSimulation(self.m) as sim:
            sim.add_sync_process(self.source)
            sim.add_sync_process(self.target)
