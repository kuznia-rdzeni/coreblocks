from itertools import product
import random
import itertools
from operator import and_
from functools import reduce
from amaranth.sim import Settle, Passive
from parameterized import parameterized, parameterized_class
from typing import TypeAlias, Callable, Optional
from collections import defaultdict, deque

from amaranth import *
from coreblocks.transactions import *
from coreblocks.transactions.core import RecordDict
from coreblocks.transactions.lib import *
from coreblocks.utils import *
from coreblocks.utils._typing import LayoutLike, ModuleLike
from coreblocks.utils import ModuleConnector
from ..common import (
    SimpleTestCircuit,
    TestCaseWithSimulator,
    TestbenchIO,
    data_layout,
    def_method_mock,
    MethodMock,
    CondVar,
    Now,
    SimBarrier,
    generate_based_on_layout,
)


class RevConnect(Elaboratable):
    def __init__(self, layout: LayoutLike):
        self.connect = Connect(rev_layout=layout)
        self.read = self.connect.write
        self.write = self.connect.read

    def elaborate(self, platform):
        return self.connect


FIFO_Like: TypeAlias = FIFO | Forwarder | Connect | RevConnect | Register


class TestFifoBase(TestCaseWithSimulator):
    def do_test_fifo(
        self,
        fifo_class: type[FIFO_Like],
        writer_rand: int = 0,
        reader_rand: int = 0,
        fifo_kwargs: dict = {},
        timeout: Optional[int] = None,
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

        if timeout is not None:
            ctx = self.run_simulation(m, timeout)
        else:
            ctx = self.run_simulation(m)

        with ctx as sim:
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


class TestRegister(TestFifoBase):
    @parameterized.expand([(0, 0), (2, 0), (0, 2), (1, 1)])
    def test_fifo(self, writer_rand, reader_rand):
        self.do_test_fifo(Register, writer_rand=writer_rand, reader_rand=reader_rand)

    def test_pipelining(self):
        self.do_test_fifo(Register, writer_rand=0, reader_rand=0, timeout=258)


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

        data_dict: dict[int, int] = dict((i, 0) for i in range(max_addr))
        read_req_queue = deque()
        addr_queue = deque()

        random.seed(seed)

        def random_wait(rand: int):
            yield from self.tick(random.randrange(rand) + 1)

        def writer():
            for i in range(test_count):
                d = random.randrange(2**data_width)
                a = random.randrange(max_addr)
                yield from m.write.call(data=d, addr=a)
                for i in range(2):
                    yield Settle()
                data_dict[a] = d
                yield from random_wait(writer_rand)

        def reader_req():
            for i in range(test_count):
                a = random.randrange(max_addr)
                yield from m.read_req.call(addr=a)
                for i in range(1):
                    yield Settle()
                if safe_writes:
                    d = data_dict[a]
                    read_req_queue.append(d)
                else:
                    addr_queue.append((i, a))
                yield from random_wait(reader_req_rand)

        def reader_resp():
            for i in range(test_count):
                while not read_req_queue:
                    yield from random_wait(reader_resp_rand)
                d = read_req_queue.popleft()
                self.assertEqual((yield from m.read_resp.call()), {"data": d})
                yield from random_wait(reader_resp_rand)

        def internal_reader_resp():
            assert m._dut._internal_read_resp_trans is not None
            yield Passive()
            while True:
                if addr_queue:
                    instr, a = addr_queue[0]
                else:
                    yield
                    continue
                d = data_dict[a]
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
            self.assertEqual(d1, ret_d1)
            yield
            ret_d2 = (yield from m.read_resp.call_result())["data"]
            self.assertEqual(d2, ret_d2)

        with self.run_simulation(m) as sim:
            sim.add_sync_process(process)


class ManyToOneConnectTransTestCircuit(Elaboratable):
    def __init__(self, count: int, lay: LayoutLike):
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
        m = TModule()

        layout = data_layout(self.iosize)

        def itransform_rec(m: ModuleLike, v: Record) -> Record:
            s = Record.like(v)
            m.d.comb += s.data.eq(v.data + 1)
            return s

        def otransform_rec(m: ModuleLike, v: Record) -> Record:
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


class TestMethodFilter(TestCaseWithSimulator):
    def initialize(self):
        self.iosize = 4
        self.layout = data_layout(self.iosize)
        self.target = TestbenchIO(Adapter(i=self.layout, o=self.layout))

    def source(self):
        for i in range(2**self.iosize):
            v = yield from self.tc.method.call(data=i)
            if i & 1:
                self.assertEqual(v["data"], (i + 1) & ((1 << self.iosize) - 1))
            else:
                self.assertEqual(v["data"], 0)

    @def_method_mock(lambda self: self.target, sched_prio=2)
    def target_mock(self, data):
        return {"data": data + 1}

    @def_method_mock(lambda self: self.cmeth, sched_prio=1)
    def cmeth_mock(self, data):
        return {"data": data % 2}

    def test_method_filter_with_methods(self):
        self.initialize()
        self.cmeth = TestbenchIO(Adapter(i=self.layout, o=data_layout(1)))
        self.tc = SimpleTestCircuit(MethodFilter(self.target.adapter.iface, self.cmeth.adapter.iface))
        m = ModuleConnector(test_circuit=self.tc, target=self.target, cmeth=self.cmeth)
        with self.run_simulation(m) as sim:
            sim.add_sync_process(self.source)
            sim.add_sync_process(self.target_mock)
            sim.add_sync_process(self.cmeth_mock)

    def test_method_filter(self):
        self.initialize()

        def condition(_, v):
            return v[0]

        self.tc = SimpleTestCircuit(MethodFilter(self.target.adapter.iface, condition))
        m = ModuleConnector(test_circuit=self.tc, target=self.target)
        with self.run_simulation(m) as sim:
            sim.add_sync_process(self.source)
            sim.add_sync_process(self.target_mock)


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


class TestSerializer(TestCaseWithSimulator):
    def test_serial(self):
        test_count = 100

        port_count = 2
        data_width = 5

        requestor_rand = 4

        layout = [("field", data_width)]

        self.req_method = TestbenchIO(Adapter(i=layout))
        self.resp_method = TestbenchIO(Adapter(o=layout))

        self.test_circuit = SimpleTestCircuit(
            Serializer(
                port_count=port_count,
                serialized_req_method=self.req_method.adapter.iface,
                serialized_resp_method=self.resp_method.adapter.iface,
            )
        )
        m = ModuleConnector(test_circuit=self.test_circuit, req_method=self.req_method, resp_method=self.resp_method)

        random.seed(14)

        serialized_data = deque()
        port_data = [deque() for _ in range(port_count)]

        got_request = False

        def random_wait(rand: int):
            yield from self.tick(random.randrange(rand) + 1)

        @def_method_mock(lambda: self.req_method, enable=lambda: not got_request)
        def serial_req_mock(field):
            nonlocal got_request
            serialized_data.append(field)
            got_request = True

        @def_method_mock(lambda: self.resp_method, enable=lambda: got_request)
        def serial_resp_mock():
            nonlocal got_request
            got_request = False
            return {"field": serialized_data[-1]}

        def requestor(i: int):
            def f():
                for _ in range(test_count):
                    d = random.randrange(2**data_width)
                    yield from self.test_circuit.serialize_in[i].call(field=d)
                    port_data[i].append(d)
                    yield from random_wait(requestor_rand)

            return f

        def responder(i: int):
            def f():
                for _ in range(test_count):
                    data_out = yield from self.test_circuit.serialize_out[i].call()
                    self.assertEqual(port_data[i].popleft(), data_out["field"])
                    yield from random_wait(requestor_rand)

            return f

        with self.run_simulation(m) as sim:
            sim.add_sync_process(serial_req_mock)
            sim.add_sync_process(serial_resp_mock)
            for i in range(port_count):
                sim.add_sync_process(requestor(i))
                sim.add_sync_process(responder(i))


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
                    self.assertEqual(val, {"data": (active_targets * data + adds) & ((1 << iosize) - 1)})
                else:
                    self.assertEqual(val, {})

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

        m.submodules.product = product = MethodTryProduct(methods, combiner)

        m.submodules.method = self.method = TestbenchIO(AdapterTrans(product.method))

        return m


class ConditionTestCircuit(Elaboratable):
    def __init__(self, target: Method, *, nonblocking: bool, priority: bool, catchall: bool):
        self.target = target
        self.source = Method(i=[("cond1", 1), ("cond2", 1), ("cond3", 1)])
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


class ConditionTest(TestCaseWithSimulator):
    @parameterized.expand(product([False, True], [False, True], [False, True]))
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
                    self.assertIsNotNone(res)

                if res is None:
                    self.assertIsNone(selection)
                    self.assertFalse(catchall or nonblocking)
                    self.assertEqual((c1, c2, c3), (0, 0, 0))
                elif selection is None:
                    self.assertTrue(nonblocking)
                    self.assertEqual((c1, c2, c3), (0, 0, 0))
                elif priority:
                    self.assertEqual(selection, c1 + 2 * c2 * (1 - c1) + 3 * c3 * (1 - c2) * (1 - c1))
                else:
                    self.assertIn(selection, [c1, 2 * c2, 3 * c3])

        with self.run_simulation(m) as sim:
            sim.add_sync_process(target_process)
            sim.add_sync_process(process)

class ConnectedConditionTestCircuit(Elaboratable):
    def __init__(self, target1: Method, target2: Method, *, priority: bool, nonblocking : bool):
        self.target1 = target1
        self.target2 = target2
        self.source = Method(i=[("cond1", 1), ("cond2", 1), ("cond3", 1)])
        self.priority = priority
        self.nonblocking = nonblocking

    def elaborate(self, platform):
        m = TModule()

        @def_method(m, self.source)
        def _(cond1, cond2, cond3):
            with connected_conditions(m, nonblocking = self.nonblocking) as cond: 
                with cond() as branch:
                    with branch(cond1):
                        self.target1(m, cond=1)
                with cond() as branch:
                    with branch(cond2):
                        self.target2(m, cond=2)
                    with branch(cond3):
                        self.target2(m, cond=3)
        return m

class ConnectedConditionTest(TestCaseWithSimulator):
    @parameterized.expand(product([False, True], [False, ])) # priority = True cause cycles in graph
    def test_condition(self, nonblocking: bool, priority: bool):
        target1 = MethodMock(i=[("cond", 2)])
        target2 = MethodMock(i=[("cond", 2)])

        circ = SimpleTestCircuit(
            ConnectedConditionTestCircuit(target1.get_method(), target2.get_method(), nonblocking=nonblocking, priority=priority)
        )
        m = ModuleConnector(test_circuit=circ, target1=target1, target2=target2)

        selection1: Optional[int]
        selection2: Optional[int]

        t1_active = True
        t2_active = True

        @def_method_mock(lambda: target1, enable = lambda: t1_active, sched_prio = 1)
        def target1_process(cond):
            nonlocal selection1
            selection1 = cond

        @def_method_mock(lambda: target2, enable = lambda: t2_active, sched_prio = 1)
        def target2_process(cond):
            nonlocal selection2
            selection2 = cond

        def process():
            nonlocal selection1, selection2
            nonlocal t1_active, t2_active
            for ta1, ta2 in product([False, True], [False, True]):
                t1_active, t2_active = ta1, ta2
                for c1, c2, c3 in product([0, 1], [0, 1], [0, 1]):
                    selection1 = None
                    selection2 = None
                    res = yield from circ.source.call_try(cond1=c1, cond2=c2, cond3=c3)
                    yield Settle()

                    if res is None:
                        self.assertIsNone(selection1)
                        self.assertIsNone(selection2)
                        if c1+c2+c3 ==0:
                            self.assertFalse(nonblocking)
                        else:
                            self.assertTrue((not t1_active and c1==1) or (not t2_active and c2+c3>0)) 
                        continue
                    if selection1 is None and selection2 is None:
                        self.assertTrue(nonblocking)
                        self.assertEqual((c1, c2, c3), (0, 0, 0))
                        continue
                    if selection1 is None:
                        self.assertEqual(c1, 0)
                        self.assertTrue(c2 != 0 or c3 !=0)
                    else:
                        self.assertEqual(c1, 1)
                    if selection2 is None:
                        self.assertEqual((c2, c3), (0,0))
                        self.assertEqual(c1, 1)
                    else:
                        if priority:
                            self.assertEqual(selection2, 2 * c2  + 3 * c3 * (1 - c2) )
                        else:
                            self.assertIn(selection2, [2 * c2, 3 * c3])

        with self.run_simulation(m) as sim:
            sim.add_sync_process(target1_process)
            sim.add_sync_process(target2_process)
            sim.add_sync_process(process)


class TestRoutingBlock(TestCaseWithSimulator):
    @staticmethod
    def prepare_any_to_any_circuit(input_count, output_count, layout):
        test_circuit = AnyToAnySimpleRoutingBlock(input_count, output_count, layout)
        m = SimpleTestCircuit(test_circuit)
        return m

    @staticmethod
    def prepare_omega_circuit(input_count, output_count, layout):
        test_circuit = OmegaRoutingNetwork(output_count, layout)
        m = SimpleTestCircuit(test_circuit)
        return m

    common_sizes = [(2, 2), (8, 8)]
    any_to_any_sizes = [(1, 1), (4, 3), (3, 5)]

    constructors = [prepare_omega_circuit, prepare_any_to_any_circuit]

    common_test_configurations = [size + (func,) for size, func in itertools.product(common_sizes, constructors)]
    any_to_any_configurations = [
        size + (func,) for size, func in itertools.product(any_to_any_sizes, [prepare_any_to_any_circuit])
    ]

    @parameterized.expand(common_test_configurations + any_to_any_configurations)
    def test_routing_block(
        self,
        input_count: int,
        output_count: int,
        prepare_test_circuit: Callable[[int, int, LayoutLike], SimpleTestCircuit],
    ):
        test_number = 100
        data_size = 5
        layout = data_layout(data_size)

        m = prepare_test_circuit(input_count, output_count, layout)

        received_data_dicts = [defaultdict(int) for i in range(output_count)]
        pending_packets = [0 for i in range(output_count)]
        senders_passive = [False for i in range(input_count)]

        def create_sender_process(k: int):
            def process():
                for i in range(test_number):
                    addr = random.randrange(output_count)
                    data = {"data": random.randrange(2**data_size)}
                    yield from m.send[k].call(addr=addr, data=data)
                    received_data_dicts[addr][data["data"]] += 1
                    pending_packets[addr] += 1
                senders_passive[k] = True

            return process

        def create_receiver_process(k: int):
            def process():
                yield Passive()
                while True:
                    res = yield from m.receive[k].call()
                    received_data_dicts[k][res["data"]] -= 1
                    pending_packets[k] -= 1

            return process

        def checker():
            while not all([pending_packets[i] == 0 for i in range(output_count)] + senders_passive):
                yield
            for d in received_data_dicts:
                for k, val in d.items():
                    self.assertEqual(val, 0)

        with self.run_simulation(m) as sim:
            for i in range(input_count):
                sim.add_sync_process(create_sender_process(i))
            for i in range(output_count):
                sim.add_sync_process(create_receiver_process(i))
            sim.add_sync_process(checker)


class TestPriorityOrderingProxy(TestCaseWithSimulator):
    def setUp(self):
        random.seed(14)
        self.test_number = 100
        self.in_size = 3
        self.out_size = 5
        self.in_lay = data_layout(self.in_size)
        self.out_lay = data_layout(self.out_size)
        self.method_count = 4  # Do not increase to more than 7, this scales up bad
        self.ordered: list[TestbenchIO] = [
            TestbenchIO(Adapter(i=self.in_lay, o=self.out_lay)) for _ in range(self.method_count)
        ]
        self.clk = 0
        self.ordered_called = {}
        self.unordered_in = {}
        self.unordered_out = {}
        self.data_pairs = []
        self.test_circuit = SimpleTestCircuit(PriorityOrderingProxyTrans([tb.adapter.iface for tb in self.ordered]))
        ordered_connector = ModuleConnector(*self.ordered)
        self.m = ModuleConnector(ordered=ordered_connector, test_circuit=self.test_circuit)

    def method_mock_generator(self, k):
        @def_method_mock(lambda: self.ordered[k])
        def f(data):
            nonlocal self
            self.ordered_called[k] = self.clk
            ans = random.randrange(2**self.out_size)
            self.data_pairs.append((data, ans))
            return {"data": ans}

        return f

    def gen_activation_list(self):
        return [random.randrange(2) for _ in range(self.method_count)]

    def call_from_activation_list(self, activation_list):
        for i in range(self.method_count):
            if activation_list[i]:
                data = random.randrange(2**self.in_size)
                self.unordered_in[i] = data
                yield from self.test_circuit.m_unordered[i].call_init({"data": data})

    def disable_all(self, activation_list):
        for i in range(self.method_count):
            if activation_list[i]:
                self.unordered_out[i] = (yield from self.test_circuit.m_unordered[i].call_result())["data"]
            yield from self.test_circuit.m_unordered[i].disable()

    def check(self, activation_list):
        for i in range(sum(activation_list)):
            self.assertEqual(self.ordered_called[i], self.clk)
            if i in self.unordered_in:
                pair_correct = (self.unordered_in[i], self.unordered_out[i])
                self.assertIn(pair_correct, self.data_pairs)
            self.data_pairs.clear()
            self.unordered_out.clear()
            self.unordered_in.clear()

    def activator(self):
        for i in range(self.test_number):
            self.clk = i
            activation_list = self.gen_activation_list()
            yield from self.call_from_activation_list(activation_list)
            yield
            yield from self.disable_all(activation_list)
            self.check(activation_list)

    def test_priority_ordering_proxy(self):
        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.activator)
            for i in range(len(self.ordered)):
                sim.add_sync_process(self.method_mock_generator(i))


class TestRegisterPipe(TestCaseWithSimulator):
    def setUp(self):
        self.test_number = 50
        self.data_width = 8
        self.layout = data_layout(self.data_width)
        self.channels = 3
        random.seed(14)

        self.circ = SimpleTestCircuit(RegisterPipe(self.layout, self.channels))

        self.virtual_regs: list[Optional[int]] = [None for _ in range(self.channels)]
        self.try_read = [False for _ in range(self.channels)]

    def input_process(self, k):
        def f():
            for _ in range(self.test_number):
                while True:
                    val = random.randrange(2**self.data_width)
                    yield Settle()
                    if all((reg is None) or try_read for reg, try_read in zip(self.virtual_regs, self.try_read)):
                        ret = yield from self.circ.write_list[k].call_try(data=val)
                        self.assertIsNotNone(ret)
                        yield Settle()
                        self.virtual_regs[k] = val
                        yield Settle()
                        break
                    else:
                        ret = yield from self.circ.write_list[k].call_try(data=val)
                        self.assertIsNone(ret)

        return f

    def output_process(self, k):
        def f():
            for _ in range(self.test_number):
                while True:
                    self.try_read[k] = True
                    data = yield from self.circ.read_list[k].call_try()
                    if (data_org := self.virtual_regs[k]) is None:
                        self.assertIsNone(data)
                    else:
                        self.assertEqual(data["data"], data_org)
                        self.virtual_regs[k] = None
                        break
                self.try_read[k] = False
                yield from self.tick(random.randrange(3))

        return f

    def test_random(self):
        with self.run_simulation(self.circ) as sim:
            for k in range(self.channels):
                sim.add_sync_process(self.input_process(k))
                sim.add_sync_process(self.output_process(k))


@parameterized_class(["transparent"], [(True,), (False,)])
class TestShiftRegister(TestCaseWithSimulator):
    transparent: bool

    def setUp(self):
        self.test_number = 50
        self.input_width = 8
        self.layout = data_layout(self.input_width)
        self.entries_number = 3
        random.seed(14)

        self.put = TestbenchIO(Adapter(i=self.layout))
        self.circ = SimpleTestCircuit(
            ShiftRegister(self.layout, self.entries_number, self.put.adapter.iface, first_transparent=self.transparent)
        )

        self.m = ModuleConnector(circ=self.circ, put=self.put)

        self.received_data = deque()
        self.expected_data = deque()

    @def_method_mock(lambda self: self.put, enable=lambda self: self.mock_enable(), sched_prio=1)
    def put_process(self, data):
        self.received_data.append(data)

    def disable_all(self):
        for k in range(self.entries_number):
            yield from self.circ.write_list[k].disable()

    def input_process(self, checker):
        def f():
            for _ in range(self.test_number):
                n = random.randrange(1, self.entries_number)
                for k in range(n):
                    val = random.randrange(2**self.input_width)
                    yield from self.circ.write_list[k].call_init(data=val)
                    self.expected_data.append(val)
                yield from checker(n)
                yield from self.disable_all()
                self.assertIterableEqual(self.expected_data, self.received_data)
                self.expected_data.clear()
                self.received_data.clear()

        return f

    def check_pipeline(self, n):
        yield Settle()
        for i in range(n - self.transparent + 1):
            yield
            yield from self.disable_all()

    def check_random(self, n):
        yield Settle()
        while len(self.received_data) < len(self.expected_data):
            yield
            if (yield from self.circ.write_list[0].done()):
                yield from self.disable_all()

    def test_pipeline(self):
        self.mock_enable = lambda: True
        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.input_process(self.check_pipeline))
            sim.add_sync_process(self.put_process)

    def test_random_wait(self):
        self.mock_enable = lambda: random.random() < 0.1
        with self.run_simulation(self.m, 3000) as sim:
            sim.add_sync_process(self.input_process(self.check_random))
            sim.add_sync_process(self.put_process)

class TestDownCounter(TestCaseWithSimulator):
    def setUp(self):
        random.seed(15)
        self.test_number = 10
        self.width = 5

        self.callback_mock = MethodMock()
        self.circ = SimpleTestCircuit(DownCounter(self.width, self.callback_mock.get_method()))
        self.m = ModuleConnector(circ = self.circ, callback = self.callback_mock)

        self.called = False

    @def_method_mock(lambda self: self.callback_mock)
    def callback_process(self):
        self.called = True
        

    def process(self):
        for _ in range(self.test_number):
            start = random.randrange(1, 2**self.width)
            yield from self.circ.set_start.call(start=start)
            while start != 0:
                self.assertFalse(self.called)
                yield from self.circ.tick.call()
                start -=1
            yield Settle()
            self.assertTrue(self.called)
            self.called = False

    def test_random(self):
        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.process)
            sim.add_sync_process(self.callback_process)

@parameterized_class(["port_count", "writer_max_wait_time"], itertools.product([1, 2, 3,], [0, 4]))
class TestBarrier(TestCaseWithSimulator):
    port_count : int
    writer_max_wait_time : int
    def setUp(self):
        random.seed(14+self.port_count+self.writer_max_wait_time)
        self.mask_count = 10
        self.test_number = 10
        self.width = 5
        self.layout = data_layout(self.width)

        self.circ = SimpleTestCircuit(Barrier(self.layout, self.port_count))

        self.mask_cond_var = CondVar(transparent = False)
        self.mask_barrier = SimBarrier(1+self.port_count)

        self.valids = 0
        self.sent = [False for _ in range(self.port_count)]
        self.data = {}

    def set_mask(self):
        self.valids = random.randrange(2**self.port_count)
        yield from self.circ.set_valids.call(valids=self.valids)

    def check_if_all_send(self):
        for i, b in enumerate(self.sent):
            if (self.valids & (1 << i)) and not b:
                return False
        return True

    def check_received_data(self, res):
        for i in range(self.port_count):
            field_name=f"out{i}"
            if not self.valids & (1 <<i):
                self.assertEqual(res[field_name]["data"], 0)
            else:
                self.assertEqual(res[field_name]["data"], self.data[i])

    def write_process_generator(self, k):
        def f():
            for mi in range(self.mask_count):
                yield from self.mask_barrier.wait()
                yield from self.mask_cond_var.wait()
                for _ in range(self.test_number):
                    if self.valids & (1<<k):
                        val = random.randrange(2**self.width)
                        yield from self.circ.write_list[k].call(data = val)
                        self.data[k] = val
                        self.sent[k] = True

                    yield from self.tick(random.randrange(self.writer_max_wait_time+1))
        return f


    def read_process(self):
        for mi in range(self.mask_count):
            yield from self.mask_barrier.wait()
            yield from self.set_mask()
            yield from self.mask_cond_var.notify()
            for _ in range(self.test_number):
                while True:
                    res = yield from self.circ.read.call_try()
                    yield Settle()
                    all_send = self.check_if_all_send()
                    if all_send:
                        self.assertIsNotNone(res)
                        break
                    else:
                        self.assertIsNone(res)
                self.check_received_data(res)
                self.sent = [False for _ in range(self.port_count)]
                self.data.clear()
                yield from self.tick(random.randrange(3))

    def test_random(self):
        with self.run_simulation(self.circ, ) as sim:
            sim.add_sync_process(self.read_process)
            for k in range(self.port_count):
                sim.add_sync_process(self.write_process_generator(k))


class TestContentAddressableMemory(TestCaseWithSimulator):
    def setUp(self):
        random.seed(14)
        self.test_number = 50
        self.addr_width = 4
        self.content_width = 5
        self.entries_count = 8
        self.addr_layout = data_layout(self.addr_width)
        self.content_layout = data_layout(self.content_width)

        self.circ = SimpleTestCircuit(ContentAddressableMemory(self.addr_layout, self.content_layout, self.entries_count))

        self.memory = {}

    def input_process(self):
        for _ in range(self.test_number):
            while True:
                addr = generate_based_on_layout(self.addr_layout)
                frozen_addr = frozenset(addr.items())
                if frozen_addr not in self.memory:
                    break
            content = generate_based_on_layout(self.content_layout)
            yield from self.circ.push.call(addr=addr, data=content)
            yield Settle()
            self.memory[frozen_addr] = content

    def output_process(self):
        yield Passive()
        while True:
            addr = generate_based_on_layout(self.addr_layout)
            res = yield from self.circ.pop.call(addr=addr)
            frozen_addr = frozenset(addr.items())
            if frozen_addr in self.memory:
                self.assertEqual(res["not_found"], 0)
                self.assertEqual(res["data"], self.memory[frozen_addr])
                self.memory.pop(frozen_addr)
            else:
                self.assertEqual(res["not_found"], 1)

    def test_random(self):
        with self.run_simulation(self.circ) as sim:
            sim.add_sync_process(self.input_process)
            sim.add_sync_process(self.output_process)
