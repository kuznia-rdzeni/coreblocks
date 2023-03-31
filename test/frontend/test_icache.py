from collections import deque
from parameterized import parameterized_class
import random

from amaranth import Elaboratable, Module
from amaranth.sim import Passive, Settle

from coreblocks.transactions import TransactionModule
from coreblocks.transactions.lib import AdapterTrans, Adapter
from coreblocks.frontend.icache import SimpleWBCacheRefiller, ICache
from coreblocks.params import GenParams, ICacheLayouts
from coreblocks.peripherals.wishbone import WishboneMaster, WishboneParameters

from ..common import TestCaseWithSimulator, TestbenchIO, test_gen_params, def_method_mock, RecordIntDictRet
from ..peripherals.test_wishbone import WishboneInterfaceWrapper


class SimpleWBCacheRefillerTestCircuit(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.gp = gen_params
        self.cp = self.gp.icache_params

    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        wb_params = WishboneParameters(
            data_width=self.gp.isa.xlen,
            addr_width=self.gp.isa.xlen,
        )
        self.wb_master = WishboneMaster(wb_params)

        self.refiller = SimpleWBCacheRefiller(self.gp.get(ICacheLayouts), self.cp, self.wb_master)

        self.start_refill = TestbenchIO(AdapterTrans(self.refiller.start_refill))
        self.accept_refill = TestbenchIO(AdapterTrans(self.refiller.accept_refill))

        m.submodules.wb_master = self.wb_master
        m.submodules.refiller = self.refiller
        m.submodules.start_refill = self.start_refill
        m.submodules.accept_refill = self.accept_refill

        self.wb_ctrl = WishboneInterfaceWrapper(self.wb_master.wbMaster)

        return tm


@parameterized_class(
    ("name", "block_size"),
    [
        ("blk_size16", 16),
        ("blk_size32", 32),
        ("blk_size64", 64),
    ],
)
class TestSimpleWBCacheRefiller(TestCaseWithSimulator):
    block_size: int

    def setUp(self) -> None:
        self.gp = test_gen_params("rv32i", icache_block_bytes=self.block_size)
        self.cp = self.gp.icache_params
        self.test_module = SimpleWBCacheRefillerTestCircuit(self.gp)

        random.seed(42)

        self.bad_addresses = set()
        self.mem = dict()

        self.requests = deque()
        for i in range(10):
            # Make the address aligned to the beginning of a cache line
            addr = random.randrange(2**self.gp.isa.xlen) & ~((1 << self.cp.offset_bits) - 1)
            self.requests.append(addr)

            if random.random() < 0.1:
                # Choose an address in this cache line to be erroneous
                bad_addr = addr + random.randrange(1 << self.cp.offset_bits)

                # Make the address aligned to the machine word size
                bad_addr = bad_addr & ~(0b11)

                self.bad_addresses.add(bad_addr)

    def wishbone_slave(self):
        yield Passive()

        while True:
            yield from self.test_module.wb_ctrl.slave_wait()

            # Wishbone is addressing words, so to get the real address we multiply it by 4
            addr = (yield self.test_module.wb_ctrl.wb.adr) << 2

            while random.random() < 0.5:
                yield

            err = 1 if addr in self.bad_addresses else 0

            data = random.randint(0, 2**32 - 1)
            self.mem[addr] = data

            yield from self.test_module.wb_ctrl.slave_respond(data, err=err)

            yield Settle()

    def refiller_process(self):
        while self.requests:
            req_addr = self.requests.pop()
            yield from self.test_module.start_refill.call(addr=req_addr)

            for i in range(self.cp.words_in_block):
                ret = yield from self.test_module.accept_refill.call()

                cur_addr = req_addr + i * 4

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
            sim.add_sync_process(self.wishbone_slave)
            sim.add_sync_process(self.refiller_process)


class ICacheTestCircuit(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.gp = gen_params
        self.cp = self.gp.icache_params

    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        # mocked cache refiller
        layouts = self.gp.get(ICacheLayouts)
        m.submodules.start_refill = self.start_refill = TestbenchIO(Adapter(i=layouts.start_refill))
        m.submodules.accept_refill = self.accept_refill = TestbenchIO(Adapter(o=layouts.accept_refill))

        m.submodules.cache = self.cache = ICache(
            layouts, self.cp, self.start_refill.adapter.iface, self.accept_refill.adapter.iface
        )
        m.submodules.issue_req = self.issue_req = TestbenchIO(AdapterTrans(self.cache.issue_req))
        m.submodules.accept_res = self.accept_res = TestbenchIO(AdapterTrans(self.cache.accept_res))
        m.submodules.flush_cache = self.flush_cache = TestbenchIO(AdapterTrans(self.cache.flush))

        return tm


@parameterized_class(
    ("name", "block_size"),
    [
        ("blk_size16", 16),
        ("blk_size64", 64),
    ],
)
class TestICache(TestCaseWithSimulator):
    block_size: int

    def setUp(self) -> None:
        random.seed(42)

        self.mem = dict()
        self.bad_addrs = set()
        self.refill_requests = deque()
        self.issued_requests = deque()

    def init_module(self, ways, sets) -> None:
        self.gp = test_gen_params("rv32i", icache_ways=ways, icache_sets=sets, icache_block_bytes=self.block_size)
        self.cp = self.gp.icache_params
        self.m = ICacheTestCircuit(self.gp)

    def refiller_processes(self):
        refill_in_fly = False
        refill_word_cnt = 0
        refill_addr = 0

        @def_method_mock(lambda: self.m.start_refill)
        def start_refill_mock(arg):
            nonlocal refill_in_fly, refill_word_cnt, refill_addr
            self.refill_requests.append(arg["addr"])
            refill_word_cnt = 0
            refill_in_fly = True
            refill_addr = arg["addr"]

        @def_method_mock(lambda: self.m.accept_refill, enable=lambda: refill_in_fly)
        def accept_refill_mock(_):
            nonlocal refill_in_fly, refill_word_cnt, refill_addr

            addr = refill_addr + refill_word_cnt * self.cp.word_width_bytes
            data = self.load_or_gen_mem(addr)
            refill_word_cnt += 1

            err = addr in self.bad_addrs
            last = refill_word_cnt == self.cp.words_in_block or err

            if last:
                refill_in_fly = False

            return {
                "addr": addr,
                "data": data,
                "error": err,
                "last": last,
            }

        return start_refill_mock, accept_refill_mock

    def load_or_gen_mem(self, addr: int):
        if addr not in self.mem:
            self.mem[addr] = random.randrange(2**self.gp.isa.xlen)
        return self.mem[addr]

    def send_req(self, addr: int):
        self.issued_requests.append(addr)
        yield from self.m.issue_req.call(addr=addr)

    def expect_resp(self, wait=False, expect_error=False):
        yield Settle()
        if wait:
            yield from self.m.accept_res.wait_until_done()

        self.assert_resp((yield from self.m.accept_res.get_outputs()), expect_error=expect_error)

    def assert_resp(self, resp: RecordIntDictRet, expect_error=False):
        addr = self.issued_requests.popleft()
        if expect_error:
            self.assertTrue(resp["error"])
        else:
            self.assertFalse(resp["error"])
            self.assertEqual(resp["instr"], self.mem[addr])

    def expect_refill(self, addr: int):
        self.assertEqual(self.refill_requests.popleft(), addr)

    def call_cache(self, addr: int, expect_error=False):
        yield from self.send_req(addr)
        yield from self.m.accept_res.enable()
        yield from self.expect_resp(wait=True, expect_error=expect_error)
        yield
        yield from self.m.accept_res.disable()

    def test_1_way(self):
        self.init_module(1, 4)

        def cache_user_process():
            # The first request should cause a cache miss
            yield from self.call_cache(0x00010004)
            self.assertEqual(self.refill_requests.pop(), 0x00010000)

            # Accesses to the same cache line shouldn't cause a cache miss
            for i in range(self.cp.words_in_block):
                yield from self.call_cache(0x00010000 + i * 4)
                self.assertEqual(len(self.refill_requests), 0)

            # Now go beyond the first cache line
            yield from self.call_cache(0x00010000 + self.cp.words_in_block * 4)
            self.assertEqual(self.refill_requests.pop(), 0x00010000 + self.cp.words_in_block * 4)

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

        start_refill_mock, accept_refill_mock = self.refiller_processes()

        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(start_refill_mock)
            sim.add_sync_process(accept_refill_mock)
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

        start_refill_mock, accept_refill_mock = self.refiller_processes()

        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(start_refill_mock)
            sim.add_sync_process(accept_refill_mock)
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

            yield from self.cycle(5)

            # Enable accept method
            yield from self.m.accept_res.enable()
            yield from self.send_req(0x00010000)

            # Response from the first request should be ready
            yield from self.expect_resp()

            # Send the second request
            yield from self.send_req(addr=0x00010004)

            # Response from the second request should be ready
            yield from self.expect_resp()

            # Try another cache line
            yield from self.send_req(addr=0x00010000 + 2 * self.cp.block_size_bytes)

            yield from self.expect_resp()
            yield from self.send_req(addr=0x00010000 + 3 * self.cp.block_size_bytes)

            # Now disable accept method
            yield from self.m.accept_res.disable()
            yield from self.send_req(addr=0x00010004)

            # Wait a few cycles. There are two requests queued
            yield from self.cycle(3)

            yield from self.m.accept_res.enable()
            yield from self.expect_resp()
            yield
            yield from self.expect_resp()
            yield from self.send_req(addr=0x0001000C)
            yield from self.expect_resp()

            yield
            yield from self.m.accept_res.disable()

            # Schedule two requests, the first one causing a cache miss
            yield from self.send_req(addr=0x00020000)
            yield from self.send_req(addr=0x00010000 + self.cp.block_size_bytes)

            yield from self.m.accept_res.enable()

            yield from self.expect_resp(wait=True)
            yield
            yield from self.expect_resp()
            yield
            yield from self.m.accept_res.disable()

            yield from self.cycle(3)

            # Schedule two requests, the second one causing a cache miss
            yield from self.send_req(addr=0x00020004)
            yield from self.send_req(addr=0x00030000 + self.cp.block_size_bytes)

            yield from self.m.accept_res.enable()

            yield from self.expect_resp(wait=True)
            yield
            yield from self.expect_resp(wait=True)
            yield
            yield from self.m.accept_res.disable()

            yield from self.cycle(3)

            # Schedule two requests, both causing a cache miss
            yield from self.send_req(addr=0x00040000)
            yield from self.send_req(addr=0x00050000 + self.cp.block_size_bytes)

            yield from self.m.accept_res.enable()

            yield from self.expect_resp(wait=True)
            yield
            yield from self.expect_resp(wait=True)
            yield
            yield from self.m.accept_res.disable()

        start_refill_mock, accept_refill_mock = self.refiller_processes()

        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(start_refill_mock)
            sim.add_sync_process(accept_refill_mock)
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
            self.mem[0x00010000] = random.randrange(2**self.gp.isa.xlen)

            # And accept the results
            self.assert_resp((yield from self.m.accept_res.call()))
            self.assert_resp((yield from self.m.accept_res.call()))
            self.expect_refill(0x00000000 + self.cp.block_size_bytes)

            # Just make sure that the line is truly flushed
            yield from self.call_cache(0x00010000)

        start_refill_mock, accept_refill_mock = self.refiller_processes()

        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(start_refill_mock)
            sim.add_sync_process(accept_refill_mock)
            sim.add_sync_process(cache_process)

    def test_errors(self):
        self.init_module(1, 4)

        def cache_process():
            self.bad_addrs.add(0x00010000)  # Bad addr at the beggining of the line
            self.bad_addrs.add(0x00020004)  # Bad addr in the middle of the line
            self.bad_addrs.add(0x00030000 + self.cp.block_size_bytes - 4)  # Bad addr at the end of the line

            yield from self.call_cache(0x00010008, expect_error=True)
            self.expect_refill(0x00010000)

            # Requesting a bad addr again should retrigger refill
            yield from self.call_cache(0x00010008, expect_error=True)
            self.expect_refill(0x00010000)

            yield from self.call_cache(0x00020000, expect_error=True)
            self.expect_refill(0x00020000)

            yield from self.call_cache(0x00030008, expect_error=True)
            self.expect_refill(0x00030000)

            # Test how pipelining works with errors

            yield from self.m.accept_res.disable()
            yield

            # Schedule two requests, the first one causing an error
            yield from self.send_req(addr=0x00020000)
            yield from self.send_req(addr=0x00011000)

            yield from self.m.accept_res.enable()

            yield from self.expect_resp(wait=True, expect_error=True)
            yield
            yield from self.expect_resp(wait=True)
            yield
            yield from self.m.accept_res.disable()

            yield from self.cycle(3)

            # Schedule two requests, the second one causing an error
            yield from self.send_req(addr=0x00021004)
            yield from self.send_req(addr=0x00030000)

            yield from self.m.accept_res.enable()

            yield from self.expect_resp(wait=True)
            yield
            yield from self.expect_resp(wait=True, expect_error=True)
            yield
            yield from self.m.accept_res.disable()

            yield from self.cycle(3)

            # Schedule two requests, both causing an error
            yield from self.send_req(addr=0x00020000)
            yield from self.send_req(addr=0x00010000)

            yield from self.m.accept_res.enable()

            yield from self.expect_resp(wait=True, expect_error=True)
            yield
            yield from self.expect_resp(wait=True, expect_error=True)
            yield
            yield from self.m.accept_res.disable()

        start_refill_mock, accept_refill_mock = self.refiller_processes()

        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(start_refill_mock)
            sim.add_sync_process(accept_refill_mock)
            sim.add_sync_process(cache_process)

    def test_random(self):
        self.init_module(4, 8)

        max_addr = 16 * self.cp.block_size_bytes * self.cp.num_of_sets
        iterations = 1000

        requests = deque()

        bad_cache_lines = set()

        for i in range(0, max_addr, 4):
            if random.random() < 0.05:
                self.bad_addrs.add(i)
                bad_cache_lines.add(i & ~((1 << self.cp.offset_bits) - 1))

        def sender():
            for _ in range(iterations):
                addr = random.randrange(0, max_addr, 4)
                yield from self.m.issue_req.call(addr=addr)
                requests.append(addr)

                while random.random() < 0.5:
                    yield

        def receiver():
            for _ in range(iterations):
                while len(requests) == 0:
                    yield

                ret = yield from self.m.accept_res.call()
                addr = requests.popleft()
                if (addr & ~((1 << self.cp.offset_bits) - 1)) in bad_cache_lines:
                    self.assertTrue(ret["error"])
                else:
                    self.assertFalse(ret["error"])
                    self.assertEqual(ret["instr"], self.mem[addr])

                while random.random() < 0.2:
                    yield

        start_refill_mock, accept_refill_mock = self.refiller_processes()

        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(start_refill_mock)
            sim.add_sync_process(accept_refill_mock)
            sim.add_sync_process(sender)
            sim.add_sync_process(receiver)
