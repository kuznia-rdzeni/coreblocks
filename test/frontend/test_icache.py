from collections import deque
from parameterized import parameterized_class
import random

from amaranth import Elaboratable, Module
from amaranth.sim import Passive, Settle
from amaranth.utils import log2_int

from transactron.lib import AdapterTrans, Adapter
from coreblocks.frontend.icache import SimpleCommonBusCacheRefiller, ICache, ICacheBypass, CacheRefillerInterface
from coreblocks.params import GenParams, ICacheLayouts
from coreblocks.params.configurations import test_core_config
from test.peripherals.bus_mock import BusMasterMock, MockBusParameteres

from ..common import TestCaseWithSimulator, TestbenchIO, def_method_mock, RecordIntDictRet


class SimpleCommonBusCacheRefillerTestCircuit(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params
        self.cp = self.gen_params.icache_params

    def elaborate(self, platform):
        m = Module()

        bus_params = MockBusParameteres(
            data_width=self.gen_params.isa.xlen,
            addr_width=self.gen_params.isa.xlen,
        )

        m.submodules.bus_master_mock = self.bus_master_mock = BusMasterMock(bus_params)

        self.refiller = SimpleCommonBusCacheRefiller(self.gen_params.get(ICacheLayouts), self.cp, self.bus_master_mock)

        self.start_refill = TestbenchIO(AdapterTrans(self.refiller.start_refill))
        self.accept_refill = TestbenchIO(AdapterTrans(self.refiller.accept_refill))

        m.submodules.refiller = self.refiller
        m.submodules.start_refill = self.start_refill
        m.submodules.accept_refill = self.accept_refill

        return m


@parameterized_class(
    ("name", "isa_xlen", "block_size"),
    [
        ("blk_size16B_rv32i", 32, 4),
        ("blk_size32B_rv32i", 32, 5),
        ("blk_size32B_rv64i", 64, 5),
        ("blk_size64B_rv32i", 32, 6),
    ],
)
class TestSimpleCommonBusCacheRefiller(TestCaseWithSimulator):
    isa_xlen: int
    block_size: int

    def setUp(self) -> None:
        self.gen_params = GenParams(
            test_core_config.replace(xlen=self.isa_xlen, icache_block_size_bits=self.block_size)
        )
        self.cp = self.gen_params.icache_params
        self.test_module = SimpleCommonBusCacheRefillerTestCircuit(self.gen_params)

        random.seed(42)

        self.bad_addresses = set()
        self.mem = dict()

        self.requests = deque()
        for _ in range(100):
            # Make the address aligned to the beginning of a cache line
            addr = random.randrange(2**self.gen_params.isa.xlen) & ~(self.cp.block_size_bytes - 1)
            self.requests.append(addr)

            if random.random() < 0.21:
                # Choose an address in this cache line to be erroneous
                bad_addr = addr + random.randrange(self.cp.block_size_bytes)

                # Make the address aligned to the machine word size
                bad_addr = bad_addr & ~(self.cp.word_width_bytes - 1)

                self.bad_addresses.add(bad_addr)

    def bus_controller(self):
        yield Passive()

        bus_master_mock = self.test_module.bus_master_mock
        bus_master_mock.activate()

        while True:
            yield from bus_master_mock.wait_for_read_request()

            # Bus is addressing words, so we need to shift it a bit to get the real address.
            addr = (yield bus_master_mock.request_read_rec.addr) << log2_int(self.cp.word_width_bytes)

            yield
            while random.random() < 0.5:
                yield

            err = 1 if addr in self.bad_addresses else 0

            data = random.randrange(2**self.gen_params.isa.xlen)
            self.mem[addr] = data

            yield from bus_master_mock.respond_to_read_request(data, err)

            yield Settle()

    def refiller_process(self):
        while self.requests:
            req_addr = self.requests.pop()
            yield from self.test_module.start_refill.call(addr=req_addr)

            for i in range(self.cp.words_in_block):
                ret = yield from self.test_module.accept_refill.call()

                cur_addr = req_addr + i * self.cp.word_width_bytes

                self.assertEqual(ret["addr"], cur_addr)

                if cur_addr in self.bad_addresses:
                    self.assertEqual(ret["error"], 1)
                    self.assertEqual(ret["last"], 1)
                    break

                self.assertEqual(ret["data"], self.mem[ret["addr"]])
                self.assertEqual(ret["error"], 0)

                last = 1 if i == self.cp.words_in_block - 1 else 0
                self.assertEqual(ret["last"], last)

    def test(self):
        with self.run_simulation(self.test_module) as sim:
            sim.add_sync_process(self.bus_controller)
            sim.add_sync_process(self.refiller_process)


class ICacheBypassTestCircuit(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params
        self.cp = self.gen_params.icache_params

    def elaborate(self, platform):
        m = Module()

        bus_params = MockBusParameteres(
            data_width=self.gen_params.isa.xlen,
            addr_width=self.gen_params.isa.xlen,
        )

        m.submodules.bus_master_mock = self.bus_master_mock = BusMasterMock(bus_params)

        m.submodules.bypass = self.bypass = ICacheBypass(
            self.gen_params.get(ICacheLayouts), self.cp, self.bus_master_mock
        )
        m.submodules.issue_req = self.issue_req = TestbenchIO(AdapterTrans(self.bypass.issue_req))
        m.submodules.accept_res = self.accept_res = TestbenchIO(AdapterTrans(self.bypass.accept_res))

        return m


@parameterized_class(
    ("name", "isa_xlen"),
    [
        ("rv32i", 32),
        ("rv64i", 64),
    ],
)
class TestICacheBypass(TestCaseWithSimulator):
    isa_xlen: str

    def setUp(self) -> None:
        self.gen_params = GenParams(test_core_config.replace(xlen=self.isa_xlen))
        self.cp = self.gen_params.icache_params
        self.m = ICacheBypassTestCircuit(self.gen_params)

        random.seed(42)

        self.mem = dict()
        self.bad_addrs = dict()

        self.requests = deque()

        # Add two consecutive addresses
        self.requests.append(0)
        self.requests.append(4)

        for _ in range(100):
            addr = random.randrange(0, 2**self.gen_params.isa.xlen, 4)
            self.requests.append(addr)

            if random.random() < 0.10:
                self.bad_addrs[addr] = True

    def load_or_gen_mem(self, addr: int):
        if addr not in self.mem:
            self.mem[addr] = random.randrange(2**self.gen_params.isa.ilen)
        return self.mem[addr]

    def bus_controller(self):
        yield Passive()

        bus_master_mock = self.m.bus_master_mock
        bus_master_mock.activate()

        while True:
            yield from bus_master_mock.wait_for_read_request()

            # Bus is addressing words, so we need to shift it a bit to get the real address.
            addr = (yield bus_master_mock.request_read_rec.addr) << log2_int(self.cp.word_width_bytes)

            while random.random() < 0.5:
                yield

            err = 1 if addr in self.bad_addrs else 0

            data = self.load_or_gen_mem(addr)
            if self.gen_params.isa.xlen == 64:
                data = self.load_or_gen_mem(addr + 4) << 32 | data

            yield from bus_master_mock.respond_to_read_request(data, err)

            yield Settle()

    def user_process(self):
        while self.requests:
            req_addr = self.requests.popleft()
            yield from self.m.issue_req.call(addr=req_addr)

            while random.random() < 0.5:
                yield

            ret = yield from self.m.accept_res.call()

            if (req_addr & ~(self.cp.word_width_bytes - 1)) in self.bad_addrs:
                self.assertTrue(ret["error"])
            else:
                self.assertFalse(ret["error"])
                self.assertEqual(ret["instr"], self.mem[req_addr])

            while random.random() < 0.5:
                yield

    def test(self):
        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.bus_controller)
            sim.add_sync_process(self.user_process)


class MockedCacheRefiller(Elaboratable, CacheRefillerInterface):
    def __init__(self, gen_params: GenParams):
        layouts = gen_params.get(ICacheLayouts)

        self.start_refill_mock = TestbenchIO(Adapter(i=layouts.start_refill))
        self.accept_refill_mock = TestbenchIO(Adapter(o=layouts.accept_refill))

        self.start_refill = self.start_refill_mock.adapter.iface
        self.accept_refill = self.accept_refill_mock.adapter.iface

    def elaborate(self, platform):
        m = Module()

        m.submodules.start_refill = self.start_refill_mock
        m.submodules.accept_refill = self.accept_refill_mock

        return m


class ICacheTestCircuit(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params
        self.cp = self.gen_params.icache_params

    def elaborate(self, platform):
        m = Module()

        m.submodules.refiller = self.refiller = MockedCacheRefiller(self.gen_params)
        m.submodules.cache = self.cache = ICache(self.gen_params.get(ICacheLayouts), self.cp, self.refiller)
        m.submodules.issue_req = self.issue_req = TestbenchIO(AdapterTrans(self.cache.issue_req))
        m.submodules.accept_res = self.accept_res = TestbenchIO(AdapterTrans(self.cache.accept_res))
        m.submodules.flush_cache = self.flush_cache = TestbenchIO(AdapterTrans(self.cache.flush))

        return m


@parameterized_class(
    ("name", "isa_xlen", "block_size"),
    [
        ("blk_size16B_rv32i", 32, 4),
        ("blk_size64B_rv32i", 32, 6),
        ("blk_size32B_rv64i", 64, 5),
    ],
)
class TestICache(TestCaseWithSimulator):
    isa_xlen: int
    block_size: int

    def setUp(self) -> None:
        random.seed(42)

        self.mem = dict()
        self.bad_addrs = set()
        self.bad_cache_lines = set()
        self.refill_requests = deque()
        self.issued_requests = deque()

        self.refill_in_fly = False
        self.refill_word_cnt = 0
        self.refill_addr = 0

    def init_module(self, ways, sets) -> None:
        self.gen_params = GenParams(
            test_core_config.replace(
                xlen=self.isa_xlen,
                icache_ways=ways,
                icache_sets_bits=log2_int(sets),
                icache_block_size_bits=self.block_size,
            )
        )
        self.cp = self.gen_params.icache_params
        self.m = ICacheTestCircuit(self.gen_params)

    @def_method_mock(lambda self: self.m.refiller.start_refill_mock)
    def start_refill_mock(self, addr):
        self.refill_requests.append(addr)
        self.refill_word_cnt = 0
        self.refill_in_fly = True
        self.refill_addr = addr

    @def_method_mock(lambda self: self.m.refiller.accept_refill_mock, enable=lambda self: self.refill_in_fly)
    def accept_refill_mock(self):
        addr = self.refill_addr + self.refill_word_cnt * self.cp.word_width_bytes
        data = self.load_or_gen_mem(addr)
        if self.gen_params.isa.xlen == 64:
            data = self.load_or_gen_mem(addr + 4) << 32 | data

        self.refill_word_cnt += 1

        err = addr in self.bad_addrs
        if self.gen_params.isa.xlen == 64:
            err = err or (addr + 4) in self.bad_addrs

        last = self.refill_word_cnt == self.cp.words_in_block or err

        if last:
            self.refill_in_fly = False

        return {
            "addr": addr,
            "data": data,
            "error": err,
            "last": last,
        }

    def load_or_gen_mem(self, addr: int):
        if addr not in self.mem:
            self.mem[addr] = random.randrange(2**self.gen_params.isa.ilen)
        return self.mem[addr]

    def add_bad_addr(self, addr: int):
        self.bad_addrs.add(addr)
        self.bad_cache_lines.add(addr & ~((1 << self.cp.offset_bits) - 1))

    def send_req(self, addr: int):
        self.issued_requests.append(addr)
        yield from self.m.issue_req.call(addr=addr)

    def expect_resp(self, wait=False):
        yield Settle()
        if wait:
            yield from self.m.accept_res.wait_until_done()

        self.assert_resp((yield from self.m.accept_res.get_outputs()))

    def assert_resp(self, resp: RecordIntDictRet):
        addr = self.issued_requests.popleft()

        if (addr & ~((1 << self.cp.offset_bits) - 1)) in self.bad_cache_lines:
            self.assertTrue(resp["error"])
        else:
            self.assertFalse(resp["error"])
            self.assertEqual(resp["instr"], self.mem[addr])

    def expect_refill(self, addr: int):
        self.assertEqual(self.refill_requests.popleft(), addr)

    def call_cache(self, addr: int):
        yield from self.send_req(addr)
        yield from self.m.accept_res.enable()
        yield from self.expect_resp(wait=True)
        yield
        yield from self.m.accept_res.disable()

    def test_1_way(self):
        self.init_module(1, 4)

        def cache_user_process():
            # The first request should cause a cache miss
            yield from self.call_cache(0x00010004)
            self.expect_refill(0x00010000)

            # Accesses to the same cache line shouldn't cause a cache miss
            for i in range(self.cp.words_in_block):
                yield from self.call_cache(0x00010000 + i * 4)
                self.assertEqual(len(self.refill_requests), 0)

            # Now go beyond the first cache line
            yield from self.call_cache(0x00010000 + self.cp.block_size_bytes)
            self.expect_refill(0x00010000 + self.cp.block_size_bytes)

            # Trigger cache aliasing
            yield from self.call_cache(0x00020000)
            yield from self.call_cache(0x00010000)
            self.expect_refill(0x00020000)
            self.expect_refill(0x00010000)

            # Fill the whole cache
            for i in range(0, self.cp.block_size_bytes * self.cp.num_of_sets, 4):
                yield from self.call_cache(i)
            for i in range(self.cp.num_of_sets):
                self.expect_refill(i * self.cp.block_size_bytes)

            # Now do some accesses within the cached memory
            for i in range(50):
                yield from self.call_cache(random.randrange(0, self.cp.block_size_bytes * self.cp.num_of_sets, 4))
            self.assertEqual(len(self.refill_requests), 0)

        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(cache_user_process)

    def test_2_way(self):
        self.init_module(2, 4)

        def cache_process():
            # Fill the first set of both ways
            yield from self.call_cache(0x00010000)
            yield from self.call_cache(0x00020000)
            self.expect_refill(0x00010000)
            self.expect_refill(0x00020000)

            # And now both lines should be in the cache
            yield from self.call_cache(0x00010004)
            yield from self.call_cache(0x00020004)
            self.assertEqual(len(self.refill_requests), 0)

        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(cache_process)

    # Tests whether the cache is fully pipelined and the latency between requests and response is exactly one cycle.
    def test_pipeline(self):
        self.init_module(2, 4)

        def cache_process():
            # Fill the cache
            for i in range(self.cp.num_of_sets):
                addr = 0x00010000 + i * self.cp.block_size_bytes
                yield from self.call_cache(addr)
                self.expect_refill(addr)

            yield from self.tick(5)

            # Create a stream of requests to ensure the pipeline is working
            yield from self.m.accept_res.enable()
            for i in range(0, self.cp.num_of_sets * self.cp.block_size_bytes, 4):
                addr = 0x00010000 + i
                self.issued_requests.append(addr)

                # Send the request
                yield from self.m.issue_req.call_init(addr=addr)
                yield Settle()
                self.assertTrue((yield from self.m.issue_req.done()))

                # After a cycle the response should be ready
                yield
                yield from self.expect_resp()
                yield from self.m.issue_req.disable()

            yield
            yield from self.m.accept_res.disable()

            yield from self.tick(5)

            # Check how the cache handles queuing the requests
            yield from self.send_req(addr=0x00010000 + 3 * self.cp.block_size_bytes)
            yield from self.send_req(addr=0x00010004)

            # Wait a few cycles. There are two requests queued
            yield from self.tick(5)

            yield from self.m.accept_res.enable()
            yield from self.expect_resp()
            yield
            yield from self.expect_resp()
            yield from self.send_req(addr=0x0001000C)
            yield from self.expect_resp()

            yield
            yield from self.m.accept_res.disable()

            yield from self.tick(5)

            # Schedule two requests, the first one causing a cache miss
            yield from self.send_req(addr=0x00020000)
            yield from self.send_req(addr=0x00010000 + self.cp.block_size_bytes)

            yield from self.m.accept_res.enable()

            yield from self.expect_resp(wait=True)
            yield
            yield from self.expect_resp()
            yield
            yield from self.m.accept_res.disable()

            yield from self.tick(3)

            # Schedule two requests, the second one causing a cache miss
            yield from self.send_req(addr=0x00020004)
            yield from self.send_req(addr=0x00030000 + self.cp.block_size_bytes)

            yield from self.m.accept_res.enable()

            yield from self.expect_resp()
            yield
            yield from self.expect_resp(wait=True)
            yield
            yield from self.m.accept_res.disable()

            yield from self.tick(3)

            # Schedule two requests, both causing a cache miss
            yield from self.send_req(addr=0x00040000)
            yield from self.send_req(addr=0x00050000 + self.cp.block_size_bytes)

            yield from self.m.accept_res.enable()

            yield from self.expect_resp(wait=True)
            yield
            yield from self.expect_resp(wait=True)
            yield
            yield from self.m.accept_res.disable()

        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(cache_process)

    def test_flush(self):
        self.init_module(2, 4)

        def cache_process():
            # Fill the whole cache
            for s in range(self.cp.num_of_sets):
                for w in range(self.cp.num_of_ways):
                    addr = w * 0x00010000 + s * self.cp.block_size_bytes
                    yield from self.call_cache(addr)
                    self.expect_refill(addr)

            # Everything should be in the cache
            for s in range(self.cp.num_of_sets):
                for w in range(self.cp.num_of_ways):
                    addr = w * 0x00010000 + s * self.cp.block_size_bytes
                    yield from self.call_cache(addr)

            self.assertEqual(len(self.refill_requests), 0)

            yield from self.m.flush_cache.call()

            # The cache should be empty
            for s in range(self.cp.num_of_sets):
                for w in range(self.cp.num_of_ways):
                    addr = w * 0x00010000 + s * self.cp.block_size_bytes
                    yield from self.call_cache(addr)
                    self.expect_refill(addr)

            # Try to flush during refilling the line
            yield from self.send_req(0x00030000)
            yield from self.m.flush_cache.call()
            # We still should be able to accept the response for the last request
            self.assert_resp((yield from self.m.accept_res.call()))
            self.expect_refill(0x00030000)

            yield from self.call_cache(0x00010000)
            self.expect_refill(0x00010000)

            yield

            # Try to execute issue_req and flush_cache methods at the same time
            yield from self.m.issue_req.call_init(addr=0x00010000)
            self.issued_requests.append(0x00010000)
            yield from self.m.flush_cache.call_init()
            yield Settle()
            self.assertFalse((yield from self.m.issue_req.done()))
            self.assertTrue((yield from self.m.flush_cache.done()))
            yield
            yield from self.m.flush_cache.call_do()
            yield from self.m.issue_req.call_do()
            self.assert_resp((yield from self.m.accept_res.call()))
            self.expect_refill(0x00010000)

            yield

            # Schedule two requests and then flush
            yield from self.send_req(0x00000000 + self.cp.block_size_bytes)
            yield from self.send_req(0x00010000)
            yield from self.m.flush_cache.call()
            self.mem[0x00010000] = random.randrange(2**self.gen_params.isa.ilen)

            # And accept the results
            self.assert_resp((yield from self.m.accept_res.call()))
            self.assert_resp((yield from self.m.accept_res.call()))
            self.expect_refill(0x00000000 + self.cp.block_size_bytes)

            # Just make sure that the line is truly flushed
            yield from self.call_cache(0x00010000)
            self.expect_refill(0x00010000)

        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(cache_process)

    def test_errors(self):
        self.init_module(1, 4)

        def cache_process():
            self.add_bad_addr(0x00010000)  # Bad addr at the beggining of the line
            self.add_bad_addr(0x00020008)  # Bad addr in the middle of the line
            self.add_bad_addr(
                0x00030000 + self.cp.block_size_bytes - self.cp.word_width_bytes
            )  # Bad addr at the end of the line

            yield from self.call_cache(0x00010008)
            self.expect_refill(0x00010000)

            # Requesting a bad addr again should retrigger refill
            yield from self.call_cache(0x00010008)
            self.expect_refill(0x00010000)

            yield from self.call_cache(0x00020000)
            self.expect_refill(0x00020000)

            yield from self.call_cache(0x00030008)
            self.expect_refill(0x00030000)

            # Test how pipelining works with errors

            yield from self.m.accept_res.disable()
            yield

            # Schedule two requests, the first one causing an error
            yield from self.send_req(addr=0x00020000)
            yield from self.send_req(addr=0x00011000)

            yield from self.m.accept_res.enable()

            yield from self.expect_resp(wait=True)
            yield
            yield from self.expect_resp(wait=True)
            yield
            yield from self.m.accept_res.disable()

            yield from self.tick(3)

            # Schedule two requests, the second one causing an error
            yield from self.send_req(addr=0x00021004)
            yield from self.send_req(addr=0x00030000)

            yield from self.tick(10)

            yield from self.m.accept_res.enable()

            yield from self.expect_resp(wait=True)
            yield
            yield from self.expect_resp(wait=True)
            yield
            yield from self.m.accept_res.disable()

            yield from self.tick(3)

            # Schedule two requests, both causing an error
            yield from self.send_req(addr=0x00020000)
            yield from self.send_req(addr=0x00010000)

            yield from self.m.accept_res.enable()

            yield from self.expect_resp(wait=True)
            yield
            yield from self.expect_resp(wait=True)
            yield
            yield from self.m.accept_res.disable()

        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(cache_process)

    def test_random(self):
        self.init_module(4, 8)

        max_addr = 16 * self.cp.block_size_bytes * self.cp.num_of_sets
        iterations = 1000

        for i in range(0, max_addr, 4):
            if random.random() < 0.05:
                self.add_bad_addr(i)

        def sender():
            for _ in range(iterations):
                yield from self.send_req(random.randrange(0, max_addr, 4))

                while random.random() < 0.5:
                    yield

        def receiver():
            for _ in range(iterations):
                while len(self.issued_requests) == 0:
                    yield

                self.assert_resp((yield from self.m.accept_res.call()))

                while random.random() < 0.2:
                    yield

        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(sender)
            sim.add_sync_process(receiver)
