import pytest
from itertools import product
import random
import itertools
from operator import and_
from functools import reduce
from amaranth.sim import Settle, Passive
from typing import Optional, TypeAlias
from parameterized import parameterized
from collections import deque

from amaranth import *
from transactron import *
from transactron.lib import *
from transactron.utils._typing import ModuleLike, MethodStruct, RecordDict
from transactron.utils import ModuleConnector
from transactron.testing import (
    SimpleTestCircuit,
    TestCaseWithSimulator,
    TestbenchIO,
    data_layout,
    def_method_mock,
)


class RevConnect(Elaboratable):
    def __init__(self, layout: MethodLayout):
        self.connect = Connect(rev_layout=layout)
        self.read = self.connect.write
        self.write = self.connect.read

    def elaborate(self, platform):
        return self.connect


FIFO_Like: TypeAlias = FIFO | Forwarder | Connect | RevConnect | Pipe


class TestFifoBase(TestCaseWithSimulator):
    def do_test_fifo(
        self, fifo_class: type[FIFO_Like], writer_rand: int = 0, reader_rand: int = 0, fifo_kwargs: dict = {}
    ):
        iosize = 8

        m = SimpleTestCircuit(fifo_class(data_layout(iosize), **fifo_kwargs))

        random.seed(1337)

        def writer():
            for i in range(2**iosize):
                yield from m.write.call(data=i)
                yield from self.random_wait(writer_rand)

        def reader():
            for i in range(2**iosize):
                assert (yield from m.read.call()) == {"data": i}
                yield from self.random_wait(reader_rand)

        with self.run_simulation(m) as sim:
            sim.add_sync_process(reader)
            sim.add_sync_process(writer)


class TestFIFO(TestFifoBase):
    @parameterized.expand([(0, 0), (2, 0), (0, 2), (1, 1)])
    def test_fifo(self, writer_rand, reader_rand):
        self.do_test_fifo(FIFO, writer_rand=writer_rand, reader_rand=reader_rand, fifo_kwargs=dict(depth=4))


class TestConnect(TestFifoBase):
    @parameterized.expand([(0, 0), (2, 0), (0, 2), (1, 1)])
    def test_fifo(self, writer_rand, reader_rand):
        self.do_test_fifo(Connect, writer_rand=writer_rand, reader_rand=reader_rand)

    @parameterized.expand([(0, 0), (2, 0), (0, 2), (1, 1)])
    def test_rev_fifo(self, writer_rand, reader_rand):
        self.do_test_fifo(RevConnect, writer_rand=writer_rand, reader_rand=reader_rand)


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
            assert (yield from m.read.call_result()) == {"data": x}
            assert (yield from m.write.call_result()) is not None
            yield

        def process():
            # test forwarding behavior
            for x in range(4):
                yield from forward_check(x)

            # load the overflow buffer
            yield from m.read.disable()
            yield from m.write.call_init(data=42)
            yield Settle()
            assert (yield from m.write.call_result()) is not None
            yield

            # writes are not possible now
            yield from m.write.call_init(data=84)
            yield Settle()
            assert (yield from m.write.call_result()) is None
            yield

            # read from the overflow buffer, writes still blocked
            yield from m.read.enable()
            yield from m.write.call_init(data=111)
            yield Settle()
            assert (yield from m.read.call_result()) == {"data": 42}
            assert (yield from m.write.call_result()) is None
            yield

            # forwarding now works again
            for x in range(4):
                yield from forward_check(x)

        with self.run_simulation(m) as sim:
            sim.add_sync_process(process)


class TestPipe(TestFifoBase):
    @parameterized.expand([(0, 0), (2, 0), (0, 2), (1, 1)])
    def test_fifo(self, writer_rand, reader_rand):
        self.do_test_fifo(Pipe, writer_rand=writer_rand, reader_rand=reader_rand)

    def test_pipelining(self):
        self.do_test_fifo(Pipe, writer_rand=0, reader_rand=0)


class TestMemoryBank(TestCaseWithSimulator):
    test_conf = [(9, 3, 3, 3, 14), (16, 1, 1, 3, 15), (16, 1, 1, 1, 16), (12, 3, 1, 1, 17)]

    parametrized_input = [tc + sf for tc, sf in itertools.product(test_conf, [(True,), (False,)])]

    @parameterized.expand(parametrized_input)
    def test_mem(self, max_addr, writer_rand, reader_req_rand, reader_resp_rand, seed, safe_writes):
        test_count = 200

        data_width = 6
        m = SimpleTestCircuit(
            MemoryBank(data_layout=[("data", data_width)], elem_count=max_addr, safe_writes=safe_writes)
        )

        data: list[int] = list(0 for _ in range(max_addr))
        read_req_queue = deque()
        addr_queue = deque()

        random.seed(seed)

        def writer():
            for cycle in range(test_count):
                d = random.randrange(2**data_width)
                a = random.randrange(max_addr)
                yield from m.write.call(data=d, addr=a)
                for _ in range(2):
                    yield Settle()
                data[a] = d
                yield from self.random_wait(writer_rand, min_cycle_cnt=1)

        def reader_req():
            for cycle in range(test_count):
                a = random.randrange(max_addr)
                yield from m.read_req.call(addr=a)
                for _ in range(1):
                    yield Settle()
                if safe_writes:
                    d = data[a]
                    read_req_queue.append(d)
                else:
                    addr_queue.append((cycle, a))
                yield from self.random_wait(reader_req_rand, min_cycle_cnt=1)

        def reader_resp():
            for cycle in range(test_count):
                while not read_req_queue:
                    yield from self.random_wait(reader_resp_rand, min_cycle_cnt=1)
                d = read_req_queue.popleft()
                assert (yield from m.read_resp.call()) == {"data": d}
                yield from self.random_wait(reader_resp_rand, min_cycle_cnt=1)

        def internal_reader_resp():
            assert m._dut._internal_read_resp_trans is not None
            yield Passive()
            while True:
                if addr_queue:
                    instr, a = addr_queue[0]
                else:
                    yield
                    continue
                d = data[a]
                # check when internal method has been run to capture
                # memory state for tests purposes
                if (yield m._dut._internal_read_resp_trans.grant):
                    addr_queue.popleft()
                    read_req_queue.append(d)
                yield

        with self.run_simulation(m) as sim:
            sim.add_sync_process(reader_req)
            sim.add_sync_process(reader_resp)
            sim.add_sync_process(writer)
            if not safe_writes:
                sim.add_sync_process(internal_reader_resp)

    def test_pipelined(self):
        data_width = 6
        max_addr = 9
        m = SimpleTestCircuit(MemoryBank(data_layout=[("data", data_width)], elem_count=max_addr, safe_writes=False))

        random.seed(14)

        def process():
            a = 3
            d1 = random.randrange(2**data_width)
            yield from m.write.call_init(data=d1, addr=a)
            yield from m.read_req.call_init(addr=a)
            yield
            d2 = random.randrange(2**data_width)
            yield from m.write.call_init(data=d2, addr=a)
            yield from m.read_resp.call_init()
            yield
            yield from m.write.disable()
            yield from m.read_req.disable()
            ret_d1 = (yield from m.read_resp.call_result())["data"]
            assert d1 == ret_d1
            yield
            ret_d2 = (yield from m.read_resp.call_result())["data"]
            assert d2 == ret_d2

        with self.run_simulation(m) as sim:
            sim.add_sync_process(process)


class TestAsyncMemoryBank(TestCaseWithSimulator):
    @parameterized.expand([(9, 3, 3, 14), (16, 1, 1, 15), (16, 1, 1, 16), (12, 3, 1, 17)])
    def test_mem(self, max_addr, writer_rand, reader_rand, seed):
        test_count = 200

        data_width = 6
        m = SimpleTestCircuit(AsyncMemoryBank(data_layout=[("data", data_width)], elem_count=max_addr))

        data: list[int] = list(0 for i in range(max_addr))

        random.seed(seed)

        def writer():
            for cycle in range(test_count):
                d = random.randrange(2**data_width)
                a = random.randrange(max_addr)
                yield from m.write.call(data=d, addr=a)
                for _ in range(2):
                    yield Settle()
                data[a] = d
                yield from self.random_wait(writer_rand, min_cycle_cnt=1)

        def reader():
            for cycle in range(test_count):
                a = random.randrange(max_addr)
                d = yield from m.read.call(addr=a)
                for _ in range(1):
                    yield Settle()
                expected_d = data[a]
                assert d["data"] == expected_d
                yield from self.random_wait(reader_rand, min_cycle_cnt=1)

        with self.run_simulation(m) as sim:
            sim.add_sync_process(reader)
            sim.add_sync_process(writer)


class ManyToOneConnectTransTestCircuit(Elaboratable):
    def __init__(self, count: int, lay: MethodLayout):
        self.count = count
        self.lay = lay
        self.inputs = []

    def elaborate(self, platform):
        m = TModule()

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
        m.submodules.fu_arbitration = ManyToOneConnectTrans(get_results=get_results, put_result=output.adapter.iface)

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
        self.max_wait = 4

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
                yield from self.random_wait(self.max_wait)
            self.producer_end[i] = True

        return producer

    def consumer(self):
        while reduce(and_, self.producer_end, True):
            result = yield from self.m.output.call_do()

            assert result is not None

            t = (result["field1"], result["field2"])
            assert t in self.expected_output
            if self.expected_output[t] == 1:
                del self.expected_output[t]
            else:
                self.expected_output[t] -= 1
            yield from self.random_wait(self.max_wait)

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


class MethodMapTestCircuit(Elaboratable):
    def __init__(self, iosize: int, use_methods: bool, use_dicts: bool):
        self.iosize = iosize
        self.use_methods = use_methods
        self.use_dicts = use_dicts

    def elaborate(self, platform):
        m = TModule()

        layout = data_layout(self.iosize)

        def itransform_rec(m: ModuleLike, v: MethodStruct) -> MethodStruct:
            s = Signal.like(v)
            m.d.comb += s.data.eq(v.data + 1)
            return s

        def otransform_rec(m: ModuleLike, v: MethodStruct) -> MethodStruct:
            s = Signal.like(v)
            m.d.comb += s.data.eq(v.data - 1)
            return s

        def itransform_dict(_, v: MethodStruct) -> RecordDict:
            return {"data": v.data + 1}

        def otransform_dict(_, v: MethodStruct) -> RecordDict:
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
            def _(arg: MethodStruct):
                return itransform(m, arg)

            @def_method(m, ometh)
            def _(arg: MethodStruct):
                return otransform(m, arg)

            trans = MethodMap(self.target.adapter.iface, i_transform=(layout, imeth), o_transform=(layout, ometh))
        else:
            trans = MethodMap(
                self.target.adapter.iface,
                i_transform=(layout, itransform),
                o_transform=(layout, otransform),
            )

        m.submodules.source = self.source = TestbenchIO(AdapterTrans(trans.use(m)))

        return m


class TestMethodTransformer(TestCaseWithSimulator):
    m: MethodMapTestCircuit

    def source(self):
        for i in range(2**self.m.iosize):
            v = yield from self.m.source.call(data=i)
            i1 = (i + 1) & ((1 << self.m.iosize) - 1)
            assert v["data"] == (((i1 << 1) | (i1 >> (self.m.iosize - 1))) - 1) & ((1 << self.m.iosize) - 1)

    @def_method_mock(lambda self: self.m.target)
    def target(self, data):
        return {"data": (data << 1) | (data >> (self.m.iosize - 1))}

    def test_method_transformer(self):
        self.m = MethodMapTestCircuit(4, False, False)
        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.source)
            sim.add_sync_process(self.target)

    def test_method_transformer_dicts(self):
        self.m = MethodMapTestCircuit(4, False, True)
        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.source)

    def test_method_transformer_with_methods(self):
        self.m = MethodMapTestCircuit(4, True, True)
        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.source)


class TestMethodFilter(TestCaseWithSimulator):
    def initialize(self):
        self.iosize = 4
        self.layout = data_layout(self.iosize)
        self.target = TestbenchIO(Adapter(i=self.layout, o=self.layout))
        self.cmeth = TestbenchIO(Adapter(i=self.layout, o=data_layout(1)))

    def source(self):
        for i in range(2**self.iosize):
            v = yield from self.tc.method.call(data=i)
            if i & 1:
                assert v["data"] == (i + 1) & ((1 << self.iosize) - 1)
            else:
                assert v["data"] == 0

    @def_method_mock(lambda self: self.target, sched_prio=2)
    def target_mock(self, data):
        return {"data": data + 1}

    @def_method_mock(lambda self: self.cmeth, sched_prio=1)
    def cmeth_mock(self, data):
        return {"data": data % 2}

    @parameterized.expand([(True,), (False,)])
    def test_method_filter_with_methods(self, use_condition):
        self.initialize()
        self.tc = SimpleTestCircuit(
            MethodFilter(self.target.adapter.iface, self.cmeth.adapter.iface, use_condition=use_condition)
        )
        m = ModuleConnector(test_circuit=self.tc, target=self.target, cmeth=self.cmeth)
        with self.run_simulation(m) as sim:
            sim.add_sync_process(self.source)

    @parameterized.expand([(True,), (False,)])
    def test_method_filter(self, use_condition):
        self.initialize()

        def condition(_, v):
            return v.data[0]

        self.tc = SimpleTestCircuit(MethodFilter(self.target.adapter.iface, condition, use_condition=use_condition))
        m = ModuleConnector(test_circuit=self.tc, target=self.target, cmeth=self.cmeth)
        with self.run_simulation(m) as sim:
            sim.add_sync_process(self.source)


class MethodProductTestCircuit(Elaboratable):
    def __init__(self, iosize: int, targets: int, add_combiner: bool):
        self.iosize = iosize
        self.targets = targets
        self.add_combiner = add_combiner
        self.target: list[TestbenchIO] = []

    def elaborate(self, platform):
        m = TModule()

        layout = data_layout(self.iosize)

        methods = []

        for k in range(self.targets):
            tgt = TestbenchIO(Adapter(i=layout, o=layout))
            methods.append(tgt.adapter.iface)
            self.target.append(tgt)
            m.submodules += tgt

        combiner = None
        if self.add_combiner:
            combiner = (layout, lambda _, vs: {"data": sum(x.data for x in vs)})

        product = MethodProduct(methods, combiner)

        m.submodules.method = self.method = TestbenchIO(AdapterTrans(product.use(m)))

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
                assert (yield from m.method.call_try(data=0)) is None

            # otherwise, the call succeeds
            for k in range(targets):
                method_en[k] = True
            yield

            data = random.randint(0, (1 << iosize) - 1)
            val = (yield from m.method.call(data=data))["data"]
            if add_combiner:
                assert val == (targets * data + (targets - 1) * targets // 2) & ((1 << iosize) - 1)
            else:
                assert val == data

        with self.run_simulation(m) as sim:
            sim.add_sync_process(method_process)
            for k in range(targets):
                sim.add_sync_process(target_process(k))


class TestSerializer(TestCaseWithSimulator):
    def setup_method(self):
        self.test_count = 100

        self.port_count = 2
        self.data_width = 5

        self.requestor_rand = 4

        layout = [("field", self.data_width)]

        self.req_method = TestbenchIO(Adapter(i=layout))
        self.resp_method = TestbenchIO(Adapter(o=layout))

        self.test_circuit = SimpleTestCircuit(
            Serializer(
                port_count=self.port_count,
                serialized_req_method=self.req_method.adapter.iface,
                serialized_resp_method=self.resp_method.adapter.iface,
            )
        )
        self.m = ModuleConnector(
            test_circuit=self.test_circuit, req_method=self.req_method, resp_method=self.resp_method
        )

        random.seed(14)

        self.serialized_data = deque()
        self.port_data = [deque() for _ in range(self.port_count)]

        self.got_request = False

    @def_method_mock(lambda self: self.req_method, enable=lambda self: not self.got_request)
    def serial_req_mock(self, field):
        self.serialized_data.append(field)
        self.got_request = True

    @def_method_mock(lambda self: self.resp_method, enable=lambda self: self.got_request)
    def serial_resp_mock(self):
        self.got_request = False
        return {"field": self.serialized_data[-1]}

    def requestor(self, i: int):
        def f():
            for _ in range(self.test_count):
                d = random.randrange(2**self.data_width)
                yield from self.test_circuit.serialize_in[i].call(field=d)
                self.port_data[i].append(d)
                yield from self.random_wait(self.requestor_rand, min_cycle_cnt=1)

        return f

    def responder(self, i: int):
        def f():
            for _ in range(self.test_count):
                data_out = yield from self.test_circuit.serialize_out[i].call()
                assert self.port_data[i].popleft() == data_out["field"]
                yield from self.random_wait(self.requestor_rand, min_cycle_cnt=1)

        return f

    def test_serial(self):
        with self.run_simulation(self.m) as sim:
            for i in range(self.port_count):
                sim.add_sync_process(self.requestor(i))
                sim.add_sync_process(self.responder(i))


class TestMethodTryProduct(TestCaseWithSimulator):
    @parameterized.expand([(1, False), (2, False), (5, True)])
    def test_method_try_product(self, targets: int, add_combiner: bool):
        random.seed(14)

        iosize = 8
        m = MethodTryProductTestCircuit(iosize, targets, add_combiner)

        method_en = [False] * targets

        def target_process(k: int):
            @def_method_mock(lambda: m.target[k], enable=lambda: method_en[k])
            def process(data):
                return {"data": data + k}

            return process

        def method_process():
            for i in range(2**targets):
                for k in range(targets):
                    method_en[k] = bool(i & (1 << k))

                active_targets = sum(method_en)

                yield

                data = random.randint(0, (1 << iosize) - 1)
                val = yield from m.method.call(data=data)
                if add_combiner:
                    adds = sum(k * method_en[k] for k in range(targets))
                    assert val == {"data": (active_targets * data + adds) & ((1 << iosize) - 1)}
                else:
                    assert val == {}

        with self.run_simulation(m) as sim:
            sim.add_sync_process(method_process)
            for k in range(targets):
                sim.add_sync_process(target_process(k))


class MethodTryProductTestCircuit(Elaboratable):
    def __init__(self, iosize: int, targets: int, add_combiner: bool):
        self.iosize = iosize
        self.targets = targets
        self.add_combiner = add_combiner
        self.target: list[TestbenchIO] = []

    def elaborate(self, platform):
        m = TModule()

        layout = data_layout(self.iosize)

        methods = []

        for k in range(self.targets):
            tgt = TestbenchIO(Adapter(i=layout, o=layout))
            methods.append(tgt.adapter.iface)
            self.target.append(tgt)
            m.submodules += tgt

        combiner = None
        if self.add_combiner:
            combiner = (layout, lambda _, vs: {"data": sum(Mux(s, r, 0) for (s, r) in vs)})

        product = MethodTryProduct(methods, combiner)

        m.submodules.method = self.method = TestbenchIO(AdapterTrans(product.use(m)))

        return m


class ConditionTestCircuit(Elaboratable):
    def __init__(self, target: Method, *, nonblocking: bool, priority: bool, catchall: bool):
        self.target = target
        self.source = Method(i=[("cond1", 1), ("cond2", 1), ("cond3", 1)], single_caller=True)
        self.nonblocking = nonblocking
        self.priority = priority
        self.catchall = catchall

    def elaborate(self, platform):
        m = TModule()

        @def_method(m, self.source)
        def _(cond1, cond2, cond3):
            with condition(m, nonblocking=self.nonblocking, priority=self.priority) as branch:
                with branch(cond1):
                    self.target(m, cond=1)
                with branch(cond2):
                    self.target(m, cond=2)
                with branch(cond3):
                    self.target(m, cond=3)
                if self.catchall:
                    with branch():
                        self.target(m, cond=0)

        return m


class TestCondition(TestCaseWithSimulator):
    @pytest.mark.parametrize("nonblocking", [False, True])
    @pytest.mark.parametrize("priority", [False, True])
    @pytest.mark.parametrize("catchall", [False, True])
    def test_condition(self, nonblocking: bool, priority: bool, catchall: bool):
        target = TestbenchIO(Adapter(i=[("cond", 2)]))

        circ = SimpleTestCircuit(
            ConditionTestCircuit(target.adapter.iface, nonblocking=nonblocking, priority=priority, catchall=catchall)
        )
        m = ModuleConnector(test_circuit=circ, target=target)

        selection: Optional[int]

        @def_method_mock(lambda: target)
        def target_process(cond):
            nonlocal selection
            selection = cond

        def process():
            nonlocal selection
            for c1, c2, c3 in product([0, 1], [0, 1], [0, 1]):
                selection = None
                res = yield from circ.source.call_try(cond1=c1, cond2=c2, cond3=c3)

                if catchall or nonblocking:
                    assert res is not None

                if res is None:
                    assert selection is None
                    assert not catchall or nonblocking
                    assert (c1, c2, c3) == (0, 0, 0)
                elif selection is None:
                    assert nonblocking
                    assert (c1, c2, c3) == (0, 0, 0)
                elif priority:
                    assert selection == c1 + 2 * c2 * (1 - c1) + 3 * c3 * (1 - c2) * (1 - c1)
                else:
                    assert selection in [c1, 2 * c2, 3 * c3]

        with self.run_simulation(m) as sim:
            sim.add_sync_process(process)
