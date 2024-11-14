import pytest
from itertools import product
import random
from operator import and_
from functools import reduce
from typing import Optional, TypeAlias
from parameterized import parameterized
from collections import deque

from amaranth import *
from transactron import *
from transactron.lib import *
from transactron.testing.method_mock import MethodMock
from transactron.testing.testbenchio import CallTrigger
from transactron.utils._typing import ModuleLike, MethodStruct, RecordDict
from transactron.utils import ModuleConnector
from transactron.testing import (
    SimpleTestCircuit,
    TestCaseWithSimulator,
    data_layout,
    def_method_mock,
    TestbenchIO,
    TestbenchContext,
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

        async def writer(sim: TestbenchContext):
            for i in range(2**iosize):
                await m.write.call(sim, data=i)
                await self.random_wait(sim, writer_rand)

        async def reader(sim: TestbenchContext):
            for i in range(2**iosize):
                assert (await m.read.call(sim)).data == i
                await self.random_wait(sim, reader_rand)

        with self.run_simulation(m) as sim:
            sim.add_testbench(reader)
            sim.add_testbench(writer)


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

        async def forward_check(sim: TestbenchContext, x: int):
            read_res, write_res = await CallTrigger(sim).call(m.read).call(m.write, data=x)
            assert read_res is not None and read_res.data == x
            assert write_res is not None

        async def process(sim: TestbenchContext):
            # test forwarding behavior
            for x in range(4):
                await forward_check(sim, x)

            # load the overflow buffer
            res = await m.write.call_try(sim, data=42)
            assert res is not None

            # writes are not possible now
            res = await m.write.call_try(sim, data=42)
            assert res is None

            # read from the overflow buffer, writes still blocked
            read_res, write_res = await CallTrigger(sim).call(m.read).call(m.write, data=111)
            assert read_res is not None and read_res.data == 42
            assert write_res is None

            # forwarding now works again
            for x in range(4):
                await forward_check(sim, x)

        with self.run_simulation(m) as sim:
            sim.add_testbench(process)


class TestPipe(TestFifoBase):
    @parameterized.expand([(0, 0), (2, 0), (0, 2), (1, 1)])
    def test_fifo(self, writer_rand, reader_rand):
        self.do_test_fifo(Pipe, writer_rand=writer_rand, reader_rand=reader_rand)

    def test_pipelining(self):
        self.do_test_fifo(Pipe, writer_rand=0, reader_rand=0)


class TestMemoryBank(TestCaseWithSimulator):
    test_conf = [(9, 3, 3, 3, 14), (16, 1, 1, 3, 15), (16, 1, 1, 1, 16), (12, 3, 1, 1, 17), (9, 0, 0, 0, 18)]

    @pytest.mark.parametrize("max_addr, writer_rand, reader_req_rand, reader_resp_rand, seed", test_conf)
    @pytest.mark.parametrize("transparent", [False, True])
    @pytest.mark.parametrize("read_ports", [1, 2])
    @pytest.mark.parametrize("write_ports", [1, 2])
    def test_mem(
        self,
        max_addr: int,
        writer_rand: int,
        reader_req_rand: int,
        reader_resp_rand: int,
        seed: int,
        transparent: bool,
        read_ports: int,
        write_ports: int,
    ):
        test_count = 200

        data_width = 6
        m = SimpleTestCircuit(
            MemoryBank(
                data_layout=[("data", data_width)],
                elem_count=max_addr,
                transparent=transparent,
                read_ports=read_ports,
                write_ports=write_ports,
            ),
        )

        data: list[int] = [0 for _ in range(max_addr)]
        read_req_queues = [deque() for _ in range(read_ports)]

        random.seed(seed)

        def writer(i):
            async def process(sim: TestbenchContext):
                for cycle in range(test_count):
                    d = random.randrange(2**data_width)
                    a = random.randrange(max_addr)
                    await m.writes[i].call(sim, data={"data": d}, addr=a)
                    await sim.delay(1e-9 * (i + 2 if not transparent else i))
                    data[a] = d
                    await self.random_wait(sim, writer_rand)

            return process

        def reader_req(i):
            async def process(sim: TestbenchContext):
                for cycle in range(test_count):
                    a = random.randrange(max_addr)
                    await m.read_reqs[i].call(sim, addr=a)
                    await sim.delay(1e-9 * (1 if not transparent else write_ports + 2))
                    d = data[a]
                    read_req_queues[i].append(d)
                    await self.random_wait(sim, reader_req_rand)

            return process

        def reader_resp(i):
            async def process(sim: TestbenchContext):
                for cycle in range(test_count):
                    await sim.delay(1e-9 * (write_ports + 3))
                    while not read_req_queues[i]:
                        await self.random_wait(sim, reader_resp_rand or 1, min_cycle_cnt=1)
                        await sim.delay(1e-9 * (write_ports + 3))
                    d = read_req_queues[i].popleft()
                    assert (await m.read_resps[i].call(sim)).data == d
                    await self.random_wait(sim, reader_resp_rand)

            return process

        pipeline_test = writer_rand == 0 and reader_req_rand == 0 and reader_resp_rand == 0
        max_cycles = test_count + 2 if pipeline_test else 100000

        with self.run_simulation(m, max_cycles=max_cycles) as sim:
            for i in range(read_ports):
                sim.add_testbench(reader_req(i))
                sim.add_testbench(reader_resp(i))
            for i in range(write_ports):
                sim.add_testbench(writer(i))


class TestAsyncMemoryBank(TestCaseWithSimulator):
    @pytest.mark.parametrize(
        "max_addr, writer_rand, reader_rand, seed", [(9, 3, 3, 14), (16, 1, 1, 15), (16, 1, 1, 16), (12, 3, 1, 17)]
    )
    @pytest.mark.parametrize("read_ports", [1, 2])
    @pytest.mark.parametrize("write_ports", [1, 2])
    def test_mem(self, max_addr: int, writer_rand: int, reader_rand: int, seed: int, read_ports: int, write_ports: int):
        test_count = 200

        data_width = 6
        m = SimpleTestCircuit(
            AsyncMemoryBank(
                data_layout=[("data", data_width)], elem_count=max_addr, read_ports=read_ports, write_ports=write_ports
            ),
        )

        data: list[int] = list(0 for i in range(max_addr))

        random.seed(seed)

        def writer(i):
            async def process(sim: TestbenchContext):
                for cycle in range(test_count):
                    d = random.randrange(2**data_width)
                    a = random.randrange(max_addr)
                    await m.writes[i].call(sim, data={"data": d}, addr=a)
                    await sim.delay(1e-9 * (i + 2))
                    data[a] = d
                    await self.random_wait(sim, writer_rand, min_cycle_cnt=1)

            return process

        def reader(i):
            async def process(sim: TestbenchContext):
                for cycle in range(test_count):
                    a = random.randrange(max_addr)
                    d = await m.reads[i].call(sim, addr=a)
                    await sim.delay(1e-9)
                    expected_d = data[a]
                    assert d["data"] == expected_d
                    await self.random_wait(sim, reader_rand, min_cycle_cnt=1)

            return process

        with self.run_simulation(m) as sim:
            for i in range(read_ports):
                sim.add_testbench(reader(i))
            for i in range(write_ports):
                sim.add_testbench(writer(i))


class ManyToOneConnectTransTestCircuit(Elaboratable):
    def __init__(self, count: int, lay: MethodLayout):
        self.count = count
        self.lay = lay
        self.inputs: list[TestbenchIO] = []

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
        m.submodules.output = self.output = output
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

        async def producer(sim: TestbenchContext):
            inputs = self.inputs[i]
            for field1, field2 in inputs:
                self.m.inputs[i].call_init(sim, field1=field1, field2=field2)
                await self.random_wait(sim, self.max_wait)
            self.producer_end[i] = True

        return producer

    async def consumer(self, sim: TestbenchContext):
        # TODO: this test doesn't test anything, needs to be fixed!
        while reduce(and_, self.producer_end, True):
            result = await self.m.output.call_do(sim)

            assert result is not None

            t = (result["field1"], result["field2"])
            assert t in self.expected_output
            if self.expected_output[t] == 1:
                del self.expected_output[t]
            else:
                self.expected_output[t] -= 1
            await self.random_wait(sim, self.max_wait)

    @pytest.mark.parametrize("count", [1, 4])
    def test(self, count: int):
        self.count = count
        self.initialize()
        with self.run_simulation(self.m) as sim:
            sim.add_testbench(self.consumer)
            for i in range(self.count):
                sim.add_testbench(self.generate_producer(i))


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

    async def source(self, sim: TestbenchContext):
        for i in range(2**self.m.iosize):
            v = await self.m.source.call(sim, data=i)
            i1 = (i + 1) & ((1 << self.m.iosize) - 1)
            assert v.data == (((i1 << 1) | (i1 >> (self.m.iosize - 1))) - 1) & ((1 << self.m.iosize) - 1)

    @def_method_mock(lambda self: self.m.target)
    def target(self, data):
        return {"data": (data << 1) | (data >> (self.m.iosize - 1))}

    def test_method_transformer(self):
        self.m = MethodMapTestCircuit(4, False, False)
        with self.run_simulation(self.m) as sim:
            sim.add_testbench(self.source)

    def test_method_transformer_dicts(self):
        self.m = MethodMapTestCircuit(4, False, True)
        with self.run_simulation(self.m) as sim:
            sim.add_testbench(self.source)

    def test_method_transformer_with_methods(self):
        self.m = MethodMapTestCircuit(4, True, True)
        with self.run_simulation(self.m) as sim:
            sim.add_testbench(self.source)


class TestMethodFilter(TestCaseWithSimulator):
    def initialize(self):
        self.iosize = 4
        self.layout = data_layout(self.iosize)
        self.target = TestbenchIO(Adapter(i=self.layout, o=self.layout))
        self.cmeth = TestbenchIO(Adapter(i=self.layout, o=data_layout(1)))

    async def source(self, sim: TestbenchContext):
        for i in range(2**self.iosize):
            v = await self.tc.method.call(sim, data=i)
            if i & 1:
                assert v.data == (i + 1) & ((1 << self.iosize) - 1)
            else:
                assert v.data == 0

    @def_method_mock(lambda self: self.target)
    def target_mock(self, data):
        return {"data": data + 1}

    @def_method_mock(lambda self: self.cmeth)
    def cmeth_mock(self, data):
        return {"data": data % 2}

    def test_method_filter_with_methods(self):
        self.initialize()
        self.tc = SimpleTestCircuit(MethodFilter(self.target.adapter.iface, self.cmeth.adapter.iface))
        m = ModuleConnector(test_circuit=self.tc, target=self.target, cmeth=self.cmeth)
        with self.run_simulation(m) as sim:
            sim.add_testbench(self.source)

    @parameterized.expand([(True,), (False,)])
    def test_method_filter_plain(self, use_condition):
        self.initialize()

        def condition(_, v):
            return v.data[0]

        self.tc = SimpleTestCircuit(MethodFilter(self.target.adapter.iface, condition, use_condition=use_condition))
        m = ModuleConnector(test_circuit=self.tc, target=self.target, cmeth=self.cmeth)
        with self.run_simulation(m) as sim:
            sim.add_testbench(self.source)


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
            def mock(data):
                return {"data": data + k}

            return mock()

        async def method_process(sim: TestbenchContext):
            # if any of the target methods is not enabled, call does not succeed
            for i in range(2**targets - 1):
                for k in range(targets):
                    method_en[k] = bool(i & (1 << k))

                await sim.tick()
                assert (await m.method.call_try(sim, data=0)) is None

            # otherwise, the call succeeds
            for k in range(targets):
                method_en[k] = True
            await sim.tick()

            data = random.randint(0, (1 << iosize) - 1)
            val = (await m.method.call(sim, data=data)).data
            if add_combiner:
                assert val == (targets * data + (targets - 1) * targets // 2) & ((1 << iosize) - 1)
            else:
                assert val == data

        with self.run_simulation(m) as sim:
            sim.add_testbench(method_process)
            for k in range(targets):
                self.add_mock(sim, target_process(k))


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
            ),
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
        @MethodMock.effect
        def eff():
            self.serialized_data.append(field)
            self.got_request = True

    @def_method_mock(lambda self: self.resp_method, enable=lambda self: self.got_request)
    def serial_resp_mock(self):
        @MethodMock.effect
        def eff():
            self.got_request = False

        if self.serialized_data:
            return {"field": self.serialized_data[-1]}

    def requestor(self, i: int):
        async def f(sim: TestbenchContext):
            for _ in range(self.test_count):
                d = random.randrange(2**self.data_width)
                await self.test_circuit.serialize_in[i].call(sim, field=d)
                self.port_data[i].append(d)
                await self.random_wait(sim, self.requestor_rand, min_cycle_cnt=1)

        return f

    def responder(self, i: int):
        async def f(sim: TestbenchContext):
            for _ in range(self.test_count):
                data_out = await self.test_circuit.serialize_out[i].call(sim)
                assert self.port_data[i].popleft() == data_out.field
                await self.random_wait(sim, self.requestor_rand, min_cycle_cnt=1)

        return f

    def test_serial(self):
        with self.run_simulation(self.m) as sim:
            for i in range(self.port_count):
                sim.add_testbench(self.requestor(i))
                sim.add_testbench(self.responder(i))


class TestMethodTryProduct(TestCaseWithSimulator):
    @parameterized.expand([(1, False), (2, False), (5, True)])
    def test_method_try_product(self, targets: int, add_combiner: bool):
        random.seed(14)

        iosize = 8
        m = MethodTryProductTestCircuit(iosize, targets, add_combiner)

        method_en = [False] * targets

        def target_process(k: int):
            @def_method_mock(lambda: m.target[k], enable=lambda: method_en[k])
            def mock(data):
                return {"data": data + k}

            return mock()

        async def method_process(sim: TestbenchContext):
            for i in range(2**targets):
                for k in range(targets):
                    method_en[k] = bool(i & (1 << k))

                active_targets = sum(method_en)

                await sim.tick()

                data = random.randint(0, (1 << iosize) - 1)
                val = await m.method.call(sim, data=data)
                if add_combiner:
                    adds = sum(k * method_en[k] for k in range(targets))
                    assert val.data == (active_targets * data + adds) & ((1 << iosize) - 1)
                else:
                    assert val.shape().size == 0

        with self.run_simulation(m) as sim:
            sim.add_testbench(method_process)
            for k in range(targets):
                self.add_mock(sim, target_process(k))


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
            ConditionTestCircuit(target.adapter.iface, nonblocking=nonblocking, priority=priority, catchall=catchall),
        )
        m = ModuleConnector(test_circuit=circ, target=target)

        selection: Optional[int]

        @def_method_mock(lambda: target)
        def target_process(cond):
            @MethodMock.effect
            def eff():
                nonlocal selection
                selection = cond

        async def process(sim: TestbenchContext):
            nonlocal selection
            await sim.tick()  # TODO workaround for mocks inactive in first cycle
            for c1, c2, c3 in product([0, 1], [0, 1], [0, 1]):
                selection = None
                res = await circ.source.call_try(sim, cond1=c1, cond2=c2, cond3=c3)

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
            sim.add_testbench(process)
