from collections import deque
import random
import pytest

from amaranth import Elaboratable, Module
from amaranth.utils import exact_log2

from transactron import Method, Required
from transactron.utils import ModuleConnector
from coreblocks.cache.icache import ICache, ICacheBypass, CacheRefillerInterface
from coreblocks.params import GenParams
from coreblocks.interface.layouts import ICacheLayouts
from coreblocks.params import configurations
from coreblocks.cache.refiller import SimpleCommonBusCacheRefiller

from transactron.testing import SimpleTestCircuit, TestCaseWithSimulator, def_method_mock, TestbenchContext
from transactron.testing.functions import MethodData
from transactron.testing.method_mock import MethodMock
from transactron.testing.testbenchio import CallTrigger
from ..peripherals.bus_mock import BusMockParameters, MockMasterAdapter


@pytest.mark.parametrize(
    ("isa_xlen", "line_size", "fetch_block"),
    [
        (32, 4, 2),
        (32, 5, 3),
        (64, 5, 3),
        (32, 6, 4),
        (32, 4, 4),
    ],
)
class TestSimpleCommonBusCacheRefiller(TestCaseWithSimulator):
    isa_xlen: int
    line_size: int
    fetch_block: int

    @pytest.fixture(autouse=True)
    def setup(self, isa_xlen: int, line_size: int, fetch_block: int) -> None:
        self.isa_xlen = isa_xlen
        self.line_size = line_size
        self.fetch_block = fetch_block
        self.gen_params = GenParams(
            configurations.test.replace(
                xlen=self.isa_xlen, icache_line_bytes_log=self.line_size, fetch_block_bytes_log=self.fetch_block
            )
        )
        self.cp = self.gen_params.icache_params

        bus_mock_params = BusMockParameters(
            data_width=self.gen_params.isa.xlen,
            addr_width=self.gen_params.isa.xlen,
        )
        self.bus_master_adapter = MockMasterAdapter(bus_mock_params)

        self.refiller = SimpleCommonBusCacheRefiller(
            self.gen_params.get(ICacheLayouts), self.cp, self.bus_master_adapter
        )
        self.tc = SimpleTestCircuit(self.refiller)

        self.test_module = ModuleConnector(bus_master_adapter=self.bus_master_adapter, refiller=self.tc)

        random.seed(42)

        self.bad_addresses = set()
        self.bad_fetch_blocks = set()
        self.mem = dict()

        self.requests = deque()
        for _ in range(100):
            # Make the address aligned to the beginning of a cache line
            addr = random.randrange(2**self.gen_params.phys_addr_bits) & ~(self.cp.line_size_bytes - 1)
            self.requests.append(addr)

            if random.random() < 0.21:
                # Choose an address in this cache line to be erroneous
                bad_addr = addr + random.randrange(self.cp.line_size_bytes)

                # Make the address aligned to the machine word size
                bad_addr = bad_addr & ~(self.cp.word_width_bytes - 1)

                self.bad_addresses.add(bad_addr)
                self.bad_fetch_blocks.add(bad_addr & ~(self.cp.fetch_block_bytes - 1))

    async def bus_mock(self, sim: TestbenchContext):
        while True:
            req = await self.bus_master_adapter.request_read_mock.call(sim)

            # Bus model is addressing words, so we need to shift it a bit to get the real address.
            addr = req.addr << exact_log2(self.cp.word_width_bytes)

            await self.random_wait_geom(sim, 0.5)

            err = 1 if addr in self.bad_addresses else 0

            data = random.randrange(2**self.gen_params.isa.xlen)
            self.mem[addr] = data

            await self.bus_master_adapter.get_read_response_mock.call(sim, data=data, err=err)

    async def refiller_process(self, sim: TestbenchContext):
        while self.requests:
            req_addr = self.requests.pop()
            await self.tc.start_refill.call(sim, paddr=req_addr)

            for i in range(self.cp.fetch_blocks_in_line):
                ret = await self.tc.accept_refill.call(sim)

                cur_addr = req_addr + i * self.cp.fetch_block_bytes

                assert ret["paddr"] == cur_addr

                if cur_addr in self.bad_fetch_blocks:
                    assert ret["error"] == 1
                    assert ret["last"] == 1
                    break

                fetch_block = ret["fetch_block"]
                for j in range(self.cp.words_in_fetch_block):
                    word = (fetch_block >> (j * self.cp.word_width)) & (2**self.cp.word_width - 1)
                    assert word == self.mem[cur_addr + j * self.cp.word_width_bytes]

                assert ret["error"] == 0

                last = 1 if i == self.cp.fetch_blocks_in_line - 1 else 0
                assert ret["last"] == last

    def test(self):
        with self.run_simulation(self.test_module) as sim:
            sim.add_testbench(self.bus_mock, background=True)
            sim.add_testbench(self.refiller_process)


@pytest.mark.parametrize(
    ("isa_xlen", "fetch_block"),
    [
        (32, 2),
        (64, 3),
    ],
)
class TestICacheBypass(TestCaseWithSimulator):
    isa_xlen: int
    fetch_block: int

    @pytest.fixture(autouse=True)
    def setup(self, isa_xlen: int, fetch_block: int) -> None:
        self.isa_xlen = isa_xlen
        self.fetch_block = fetch_block
        self.gen_params = GenParams(
            configurations.test.replace(xlen=self.isa_xlen, fetch_block_bytes_log=self.fetch_block, icache_enable=False)
        )
        self.cp = self.gen_params.icache_params

        bus_mock_params = BusMockParameters(
            data_width=self.gen_params.isa.xlen,
            addr_width=self.gen_params.isa.xlen,
        )
        self.bus_master_adapter = MockMasterAdapter(bus_mock_params)

        self.bypass = ICacheBypass(self.gen_params.get(ICacheLayouts), self.cp, self.bus_master_adapter)
        self.tc = SimpleTestCircuit(self.bypass)

        self.m = ModuleConnector(bus_master_adapter=self.bus_master_adapter, bypass=self.tc)

        random.seed(42)

        self.mem = dict()
        self.bad_addrs = dict()

        self.requests = deque()

        # Add two consecutive addresses
        self.requests.append(0)
        self.requests.append(4)

        for _ in range(100):
            addr = random.randrange(0, 2**self.gen_params.phys_addr_bits, 4)
            self.requests.append(addr)

            if random.random() < 0.10:
                self.bad_addrs[addr] = True

    def load_or_gen_mem(self, addr: int):
        if addr not in self.mem:
            self.mem[addr] = random.randrange(2**self.gen_params.isa.ilen)
        return self.mem[addr]

    async def bus_mock(self, sim: TestbenchContext):
        while True:
            req = await self.bus_master_adapter.request_read_mock.call(sim)

            # Bus model is addressing words, so we need to shift it a bit to get the real address.
            addr = req.addr << exact_log2(self.cp.word_width_bytes)

            await self.random_wait_geom(sim, 0.5)

            err = 1 if addr in self.bad_addrs else 0

            data = self.load_or_gen_mem(addr)
            if self.gen_params.isa.xlen == 64:
                data = self.load_or_gen_mem(addr + 4) << 32 | data

            await self.bus_master_adapter.get_read_response_mock.call(sim, data=data, err=err)

    async def user_process(self, sim: TestbenchContext):
        while self.requests:
            req_addr = self.requests.popleft() & ~(self.cp.fetch_block_bytes - 1)
            await self.tc.issue_req.call(sim, paddr=req_addr)

            await self.random_wait_geom(sim, 0.5)

            ret = await self.tc.accept_res.call(sim)

            if (req_addr & ~(self.cp.word_width_bytes - 1)) in self.bad_addrs:
                assert ret["error"]
            else:
                assert not ret["error"]

                data = self.mem[req_addr]
                if self.gen_params.isa.xlen == 64:
                    data |= self.mem[req_addr + 4] << 32
                assert ret["fetch_block"] == data

            await self.random_wait_geom(sim, 0.5)

    def test(self):
        with self.run_simulation(self.m) as sim:
            sim.add_testbench(self.bus_mock, background=True)
            sim.add_testbench(self.user_process)


class MockedCacheRefiller(Elaboratable, CacheRefillerInterface):
    start_refill: Required[Method]
    accept_refill: Required[Method]

    def __init__(self, gen_params: GenParams):
        layouts = gen_params.get(ICacheLayouts)

        self.start_refill = Method(i=layouts.start_refill)
        self.accept_refill = Method(o=layouts.accept_refill)

    def elaborate(self, platform):
        return Module()


@pytest.mark.parametrize(
    ("isa_xlen", "line_size", "fetch_block"),
    [
        (32, 4, 2),
        (32, 6, 4),
        (64, 5, 4),
        (64, 5, 5),
    ],
)
class TestICache(TestCaseWithSimulator):
    isa_xlen: int
    line_size: int
    fetch_block: int

    @pytest.fixture(autouse=True)
    def setup(self, isa_xlen: int, line_size: int, fetch_block: int) -> None:
        self.isa_xlen = isa_xlen
        self.line_size = line_size
        self.fetch_block = fetch_block
        random.seed(42)

        self.mem = dict()
        self.bad_addrs = set()
        self.bad_cache_lines = set()
        self.refill_requests = deque()
        self.refill_block_cnt = 0
        self.issued_requests = deque()

        self.accept_refill_request = True

        self.refill_in_fly = False
        self.refill_word_cnt = 0
        self.refill_addr = 0

    def init_module(self, ways, sets) -> None:
        self.gen_params = GenParams(
            configurations.test.replace(
                xlen=self.isa_xlen,
                icache_ways=ways,
                icache_sets_bits=exact_log2(sets),
                icache_line_bytes_log=self.line_size,
                fetch_block_bytes_log=self.fetch_block,
            )
        )
        self.cp = self.gen_params.icache_params
        self.refiller = MockedCacheRefiller(self.gen_params)
        self.refiller_tc = SimpleTestCircuit(self.refiller)
        self.cache = ICache(self.gen_params.get(ICacheLayouts), self.cp, self.refiller)
        self.cache_tc = SimpleTestCircuit(self.cache)
        self.m = ModuleConnector(refiller=self.refiller_tc, cache=self.cache_tc)

    @def_method_mock(lambda self: self.refiller_tc.start_refill, enable=lambda self: self.accept_refill_request)
    def start_refill_mock(self, paddr):
        @MethodMock.effect
        def eff():
            self.refill_requests.append(paddr)
            self.refill_block_cnt = 0
            self.refill_in_fly = True
            self.refill_addr = paddr

    def enen(self):
        return self.refill_in_fly

    @def_method_mock(lambda self: self.refiller_tc.accept_refill, enable=enen)
    def accept_refill_mock(self):
        addr = self.refill_addr + self.refill_block_cnt * self.cp.fetch_block_bytes

        fetch_block = 0
        bad_addr = False
        for i in range(0, self.cp.fetch_block_bytes, 4):
            fetch_block |= self.load_or_gen_mem(addr + i) << (8 * i)
            if addr + i in self.bad_addrs:
                bad_addr = True

        last = self.refill_block_cnt + 1 == self.cp.fetch_blocks_in_line or bad_addr

        @MethodMock.effect
        def eff():
            self.refill_block_cnt += 1

            if last:
                self.refill_in_fly = False

        return {
            "paddr": addr,
            "fetch_block": fetch_block,
            "error": bad_addr,
            "last": last,
        }

    def load_or_gen_mem(self, addr: int):
        if addr not in self.mem:
            self.mem[addr] = random.randrange(2**self.gen_params.isa.ilen)
        return self.mem[addr]

    def add_bad_addr(self, addr: int):
        self.bad_addrs.add(addr)
        self.bad_cache_lines.add(addr & ~((1 << self.cp.offset_bits) - 1))

    async def send_req(self, sim: TestbenchContext, addr: int):
        self.issued_requests.append(addr)
        await self.cache_tc.issue_req.call(sim, paddr=addr)

    async def expect_resp(self, sim: TestbenchContext, wait=False):
        if wait:
            *_, resp = await self.cache_tc.accept_res.sample_outputs_until_done(sim)
        else:
            *_, resp = await self.cache_tc.accept_res.sample_outputs(sim)

        self.assert_resp(resp)

    def assert_resp(self, resp: MethodData):
        addr = self.issued_requests.popleft() & ~(self.cp.fetch_block_bytes - 1)

        if (addr & ~((1 << self.cp.offset_bits) - 1)) in self.bad_cache_lines:
            assert resp["error"]
        else:
            assert not resp["error"]
            fetch_block = 0
            for i in range(0, self.cp.fetch_block_bytes, 4):
                fetch_block |= self.mem[addr + i] << (8 * i)

            assert resp["fetch_block"] == fetch_block

    def expect_refill(self, addr: int):
        assert self.refill_requests.popleft() == addr

    async def call_cache(self, sim: TestbenchContext, addr: int):
        await self.send_req(sim, addr)
        self.cache_tc.accept_res.enable(sim)
        await self.expect_resp(sim, wait=True)
        self.cache_tc.accept_res.disable(sim)

    def test_1_way(self):
        self.init_module(1, 4)

        async def cache_user_process(sim: TestbenchContext):
            # The first request should cause a cache miss
            await self.call_cache(sim, 0x00010004)
            self.expect_refill(0x00010000)

            # Accesses to the same cache line shouldn't cause a cache miss
            for i in range(self.cp.fetch_blocks_in_line):
                await self.call_cache(sim, 0x00010000 + i * self.cp.fetch_block_bytes)
                assert len(self.refill_requests) == 0

            # Now go beyond the first cache line
            await self.call_cache(sim, 0x00010000 + self.cp.line_size_bytes)
            self.expect_refill(0x00010000 + self.cp.line_size_bytes)

            # Trigger cache aliasing
            await self.call_cache(sim, 0x00020000)
            await self.call_cache(sim, 0x00010000)
            self.expect_refill(0x00020000)
            self.expect_refill(0x00010000)

            # Fill the whole cache
            for i in range(0, self.cp.line_size_bytes * self.cp.num_of_sets, 4):
                await self.call_cache(sim, i)
            for i in range(self.cp.num_of_sets):
                self.expect_refill(i * self.cp.line_size_bytes)

            # Now do some accesses within the cached memory
            for i in range(50):
                await self.call_cache(sim, random.randrange(0, self.cp.line_size_bytes * self.cp.num_of_sets, 4))
            assert len(self.refill_requests) == 0

        with self.run_simulation(self.m) as sim:
            sim.add_testbench(cache_user_process)

    def test_2_way(self):
        self.init_module(2, 4)

        async def cache_process(sim: TestbenchContext):
            # Fill the first set of both ways
            await self.call_cache(sim, 0x00010000)
            await self.call_cache(sim, 0x00020000)
            self.expect_refill(0x00010000)
            self.expect_refill(0x00020000)

            # And now both lines should be in the cache
            await self.call_cache(sim, 0x00010004)
            await self.call_cache(sim, 0x00020004)
            assert len(self.refill_requests) == 0

        with self.run_simulation(self.m) as sim:
            sim.add_testbench(cache_process)

    # Tests whether the cache is fully pipelined and the latency between requests and response is exactly one cycle.
    def test_pipeline(self):
        self.init_module(2, 4)

        async def cache_process(sim: TestbenchContext):
            # Fill the cache
            for i in range(self.cp.num_of_sets):
                addr = 0x00010000 + i * self.cp.line_size_bytes
                await self.call_cache(sim, addr)
                self.expect_refill(addr)

            await self.tick(sim, 4)

            # Create a stream of requests to ensure the pipeline is working
            self.cache_tc.accept_res.enable(sim)
            for i in range(0, self.cp.num_of_sets * self.cp.line_size_bytes, 4):
                addr = 0x00010000 + i
                self.issued_requests.append(addr)

                # Send the request
                ret = await self.cache_tc.issue_req.call_try(sim, paddr=addr)
                assert ret is not None

                # After a cycle the response should be ready
                await self.expect_resp(sim)

            self.cache_tc.accept_res.disable(sim)

            await self.tick(sim, 4)

            # Check how the cache handles queuing the requests
            await self.send_req(sim, 0x00010000 + 3 * self.cp.line_size_bytes)
            await self.send_req(sim, 0x00010004)

            # Wait a few cycles. There are two requests queued
            await self.tick(sim, 4)

            self.cache_tc.accept_res.enable(sim)
            await self.expect_resp(
                sim,
            )
            await self.expect_resp(
                sim,
            )
            await self.send_req(sim, 0x0001000C)
            await self.expect_resp(
                sim,
            )

            self.cache_tc.accept_res.disable(sim)

            await self.tick(sim, 4)

            # Schedule two requests, the first one causing a cache miss
            await self.send_req(sim, 0x00020000)
            await self.send_req(sim, 0x00010000 + self.cp.line_size_bytes)

            self.cache_tc.accept_res.enable(sim)

            await self.expect_resp(sim, wait=True)
            await self.expect_resp(
                sim,
            )
            self.cache_tc.accept_res.disable(sim)

            await self.tick(sim, 2)

            # Schedule two requests, the second one causing a cache miss
            await self.send_req(sim, 0x00020004)
            await self.send_req(sim, 0x00030000 + self.cp.line_size_bytes)

            self.cache_tc.accept_res.enable(sim)

            await self.expect_resp(
                sim,
            )
            await self.expect_resp(sim, wait=True)
            self.cache_tc.accept_res.disable(sim)

            await self.tick(sim, 2)

            # Schedule two requests, both causing a cache miss
            await self.send_req(sim, 0x00040000)
            await self.send_req(sim, 0x00050000 + self.cp.line_size_bytes)

            self.cache_tc.accept_res.enable(sim)

            await self.expect_resp(sim, wait=True)
            await self.expect_resp(sim, wait=True)
            self.cache_tc.accept_res.disable(sim)

        with self.run_simulation(self.m) as sim:
            sim.add_testbench(cache_process)

    def test_flush(self):
        self.init_module(2, 4)

        async def cache_process(sim: TestbenchContext):
            # Fill the whole cache
            for s in range(self.cp.num_of_sets):
                for w in range(self.cp.num_of_ways):
                    addr = w * 0x00010000 + s * self.cp.line_size_bytes
                    await self.call_cache(sim, addr)
                    self.expect_refill(addr)

            # Everything should be in the cache
            for s in range(self.cp.num_of_sets):
                for w in range(self.cp.num_of_ways):
                    addr = w * 0x00010000 + s * self.cp.line_size_bytes
                    await self.call_cache(sim, addr)

            assert len(self.refill_requests) == 0

            await self.cache_tc.flush.call(sim)

            # The cache should be empty
            for s in range(self.cp.num_of_sets):
                for w in range(self.cp.num_of_ways):
                    addr = w * 0x00010000 + s * self.cp.line_size_bytes
                    await self.call_cache(sim, addr)
                    self.expect_refill(addr)

            # Try to flush during refilling the line
            await self.send_req(sim, 0x00030000)
            await self.cache_tc.flush.call(sim)
            # We still should be able to accept the response for the last request
            self.assert_resp(await self.cache_tc.accept_res.call(sim))
            self.expect_refill(0x00030000)

            await self.call_cache(sim, 0x00010000)
            self.expect_refill(0x00010000)

            # Try to execute issue_req and flush_cache methods at the same time
            self.issued_requests.append(0x00010000)
            issue_req_res, flush_cache_res = (
                await CallTrigger(sim).call(self.cache_tc.issue_req, paddr=0x00010000).call(self.cache_tc.flush)
            )
            assert issue_req_res is None
            assert flush_cache_res is not None
            await self.cache_tc.issue_req.call(sim, paddr=0x00010000)
            self.assert_resp(await self.cache_tc.accept_res.call(sim))
            self.expect_refill(0x00010000)

            # Schedule two requests and then flush
            await self.send_req(sim, 0x00000000 + self.cp.line_size_bytes)
            await self.send_req(sim, 0x00010000)

            res = await self.cache_tc.flush.call_try(sim)
            # We cannot flush until there are two pending requests
            assert res is None
            res = await self.cache_tc.flush.call_try(sim)
            assert res is None

            # Accept the first response
            self.assert_resp(await self.cache_tc.accept_res.call(sim))

            await self.cache_tc.flush.call(sim)

            # And accept the second response ensuring that we got old data
            self.assert_resp(await self.cache_tc.accept_res.call(sim))
            self.expect_refill(0x00000000 + self.cp.line_size_bytes)

            # Just make sure that the line is truly flushed
            await self.call_cache(sim, 0x00010000)
            self.expect_refill(0x00010000)

        with self.run_simulation(self.m) as sim:
            sim.add_testbench(cache_process)

    def test_errors(self):
        self.init_module(1, 4)

        async def cache_process(sim: TestbenchContext):
            self.add_bad_addr(0x00010000)  # Bad addr at the beginning of the line
            self.add_bad_addr(0x00020008)  # Bad addr in the middle of the line
            self.add_bad_addr(
                0x00030000 + self.cp.line_size_bytes - self.cp.word_width_bytes
            )  # Bad addr at the end of the line

            await self.call_cache(sim, 0x00010008)
            self.expect_refill(0x00010000)

            # Requesting a bad addr again should retrigger refill
            await self.call_cache(sim, 0x00010008)
            self.expect_refill(0x00010000)

            await self.call_cache(sim, 0x00020000)
            self.expect_refill(0x00020000)

            await self.call_cache(sim, 0x00030008)
            self.expect_refill(0x00030000)

            # Test how pipelining works with errors

            self.cache_tc.accept_res.disable(sim)

            # Schedule two requests, the first one causing an error
            await self.send_req(sim, 0x00020000)
            await self.send_req(sim, 0x00011000)

            self.cache_tc.accept_res.enable(sim)

            await self.expect_resp(sim, wait=True)
            await self.expect_resp(sim, wait=True)
            self.cache_tc.accept_res.disable(sim)

            await self.tick(sim, 3)

            # Schedule two requests, the second one causing an error
            await self.send_req(sim, 0x00021004)
            await self.send_req(sim, 0x00030000)

            await self.tick(sim, 10)

            self.cache_tc.accept_res.enable(sim)

            await self.expect_resp(sim, wait=True)
            await self.expect_resp(sim, wait=True)
            self.cache_tc.accept_res.disable(sim)

            await self.tick(sim, 3)

            # Schedule two requests, both causing an error
            await self.send_req(sim, 0x00020000)
            await self.send_req(sim, 0x00010000)

            self.cache_tc.accept_res.enable(sim)

            await self.expect_resp(sim, wait=True)
            await self.expect_resp(sim, wait=True)
            self.cache_tc.accept_res.disable(sim)

            # The second request will cause an error
            await self.send_req(sim, 0x00021004)
            await self.send_req(sim, 0x00030000)

            await self.tick(sim, 10)

            # Accept the first response
            self.cache_tc.accept_res.enable(sim)
            await self.expect_resp(sim, wait=True)

            # Wait before accepting the second response
            self.cache_tc.accept_res.disable(sim)
            await self.tick(sim, 10)
            self.cache_tc.accept_res.enable(sim)
            await self.expect_resp(sim, wait=True)

            # This request should not cause an error
            await self.send_req(sim, 0x00011000)
            await self.expect_resp(sim, wait=True)

        with self.run_simulation(self.m) as sim:
            sim.add_testbench(cache_process)

    def test_random(self):
        self.init_module(4, 8)

        max_addr = 16 * self.cp.line_size_bytes * self.cp.num_of_sets
        iterations = 1000

        for i in range(0, max_addr, 4):
            if random.random() < 0.05:
                self.add_bad_addr(i)

        async def refiller_ctrl(sim: TestbenchContext):
            while True:
                await self.random_wait_geom(sim, 0.4)
                self.accept_refill_request = False

                await self.random_wait_geom(sim, 0.7)
                self.accept_refill_request = True

        async def sender(sim: TestbenchContext):
            for _ in range(iterations):
                await self.send_req(sim, random.randrange(0, max_addr, 4))
                await self.random_wait_geom(sim, 0.5)

        async def receiver(sim: TestbenchContext):
            for _ in range(iterations):
                while len(self.issued_requests) == 0:
                    await sim.tick()

                self.assert_resp(await self.cache_tc.accept_res.call(sim))
                await self.random_wait_geom(sim, 0.2)

        with self.run_simulation(self.m) as sim:
            sim.add_testbench(sender)
            sim.add_testbench(receiver)
            sim.add_testbench(refiller_ctrl, background=True)
