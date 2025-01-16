from collections import deque
from parameterized import parameterized_class
import random

from amaranth import Elaboratable, Module
from amaranth.utils import exact_log2

from transactron.lib import AdapterTrans, Adapter
from coreblocks.cache.icache import ICache, ICacheBypass, CacheRefillerInterface
from coreblocks.params import GenParams
from coreblocks.interface.layouts import ICacheLayouts
from coreblocks.params.configurations import test_core_config
from coreblocks.cache.refiller import SimpleCommonBusCacheRefiller

from transactron.testing import TestCaseWithSimulator, TestbenchIO, def_method_mock, TestbenchContext
from transactron.testing.functions import MethodData
from transactron.testing.method_mock import MethodMock
from transactron.testing.testbenchio import CallTrigger
from ..peripherals.bus_mock import BusMockParameters, MockMasterAdapter


class SimpleCommonBusCacheRefillerTestCircuit(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params
        self.cp = self.gen_params.icache_params

    def elaborate(self, platform):
        m = Module()

        bus_mock_params = BusMockParameters(
            data_width=self.gen_params.isa.xlen,
            addr_width=self.gen_params.isa.xlen,
        )
        self.bus_master_adapter = MockMasterAdapter(bus_mock_params)

        self.refiller = SimpleCommonBusCacheRefiller(
            self.gen_params.get(ICacheLayouts), self.cp, self.bus_master_adapter
        )

        self.start_refill = TestbenchIO(AdapterTrans(self.refiller.start_refill))
        self.accept_refill = TestbenchIO(AdapterTrans(self.refiller.accept_refill))

        m.submodules.bus_master_adapter = self.bus_master_adapter
        m.submodules.refiller = self.refiller
        m.submodules.start_refill = self.start_refill
        m.submodules.accept_refill = self.accept_refill

        return m


@parameterized_class(
    ("name", "isa_xlen", "line_size", "fetch_block"),
    [
        ("line16B_block4B_rv32i", 32, 4, 2),
        ("line32B_block8B_rv32i", 32, 5, 3),
        ("line32B_block8B_rv64i", 64, 5, 3),
        ("line64B_block16B_rv32i", 32, 6, 4),
        ("line16B_block16B_rv32i", 32, 4, 4),
    ],
)
class TestSimpleCommonBusCacheRefiller(TestCaseWithSimulator):
    isa_xlen: int
    line_size: int
    fetch_block: int

    def setup_method(self) -> None:
        self.gen_params = GenParams(
            test_core_config.replace(
                xlen=self.isa_xlen, icache_line_bytes_log=self.line_size, fetch_block_bytes_log=self.fetch_block
            )
        )
        self.cp = self.gen_params.icache_params
        self.test_module = SimpleCommonBusCacheRefillerTestCircuit(self.gen_params)

        random.seed(42)

        self.bad_addresses = set()
        self.bad_fetch_blocks = set()
        self.mem = dict()

        self.requests = deque()
        for _ in range(100):
            # Make the address aligned to the beginning of a cache line
            addr = random.randrange(2**self.gen_params.isa.xlen) & ~(self.cp.line_size_bytes - 1)
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
            req = await self.test_module.bus_master_adapter.request_read_mock.call(sim)

            # Bus model is addressing words, so we need to shift it a bit to get the real address.
            addr = req.addr << exact_log2(self.cp.word_width_bytes)

            await self.random_wait_geom(sim, 0.5)

            err = 1 if addr in self.bad_addresses else 0

            data = random.randrange(2**self.gen_params.isa.xlen)
            self.mem[addr] = data

            await self.test_module.bus_master_adapter.get_read_response_mock.call(sim, data=data, err=err)

    async def refiller_process(self, sim: TestbenchContext):
        while self.requests:
            req_addr = self.requests.pop()
            await self.test_module.start_refill.call(sim, addr=req_addr)

            for i in range(self.cp.fetch_blocks_in_line):
                ret = await self.test_module.accept_refill.call(sim)

                cur_addr = req_addr + i * self.cp.fetch_block_bytes

                assert ret["addr"] == cur_addr

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


class ICacheBypassTestCircuit(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params
        self.cp = self.gen_params.icache_params

    def elaborate(self, platform):
        m = Module()

        bus_mock_params = BusMockParameters(
            data_width=self.gen_params.isa.xlen,
            addr_width=self.gen_params.isa.xlen,
        )

        m.submodules.bus_master_adapter = self.bus_master_adapter = MockMasterAdapter(bus_mock_params)
        m.submodules.bypass = self.bypass = ICacheBypass(
            self.gen_params.get(ICacheLayouts), self.cp, self.bus_master_adapter
        )
        m.submodules.issue_req = self.issue_req = TestbenchIO(AdapterTrans(self.bypass.issue_req))
        m.submodules.accept_res = self.accept_res = TestbenchIO(AdapterTrans(self.bypass.accept_res))

        return m


@parameterized_class(
    ("name", "isa_xlen", "fetch_block"),
    [
        ("rv32i", 32, 2),
        ("rv64i", 64, 3),
    ],
)
class TestICacheBypass(TestCaseWithSimulator):
    isa_xlen: int
    fetch_block: int

    def setup_method(self) -> None:
        self.gen_params = GenParams(
            test_core_config.replace(xlen=self.isa_xlen, fetch_block_bytes_log=self.fetch_block, icache_enable=False)
        )
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

    async def bus_mock(self, sim: TestbenchContext):
        while True:
            req = await self.m.bus_master_adapter.request_read_mock.call(sim)

            # Bus model is addressing words, so we need to shift it a bit to get the real address.
            addr = req.addr << exact_log2(self.cp.word_width_bytes)

            await self.random_wait_geom(sim, 0.5)

            err = 1 if addr in self.bad_addrs else 0

            data = self.load_or_gen_mem(addr)
            if self.gen_params.isa.xlen == 64:
                data = self.load_or_gen_mem(addr + 4) << 32 | data

            await self.m.bus_master_adapter.get_read_response_mock.call(sim, data=data, err=err)

    async def user_process(self, sim: TestbenchContext):
        while self.requests:
            req_addr = self.requests.popleft() & ~(self.cp.fetch_block_bytes - 1)
            await self.m.issue_req.call(sim, addr=req_addr)

            await self.random_wait_geom(sim, 0.5)

            ret = await self.m.accept_res.call(sim)

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
    def __init__(self, gen_params: GenParams):
        layouts = gen_params.get(ICacheLayouts)

        self.start_refill_mock = TestbenchIO(Adapter.create(i=layouts.start_refill))
        self.accept_refill_mock = TestbenchIO(Adapter.create(o=layouts.accept_refill))

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
    ("name", "isa_xlen", "line_size", "fetch_block"),
    [
        ("line16B_block8B_rv32i", 32, 4, 2),
        ("line64B_block16B_rv32i", 32, 6, 4),
        ("line32B_block16B_rv64i", 64, 5, 4),
        ("line32B_block32B_rv64i", 64, 5, 5),
    ],
)
class TestICache(TestCaseWithSimulator):
    isa_xlen: int
    line_size: int
    fetch_block: int

    def setup_method(self) -> None:
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
            test_core_config.replace(
                xlen=self.isa_xlen,
                icache_ways=ways,
                icache_sets_bits=exact_log2(sets),
                icache_line_bytes_log=self.line_size,
                fetch_block_bytes_log=self.fetch_block,
            )
        )
        self.cp = self.gen_params.icache_params
        self.m = ICacheTestCircuit(self.gen_params)

    @def_method_mock(lambda self: self.m.refiller.start_refill_mock, enable=lambda self: self.accept_refill_request)
    def start_refill_mock(self, addr):
        @MethodMock.effect
        def eff():
            self.refill_requests.append(addr)
            self.refill_block_cnt = 0
            self.refill_in_fly = True
            self.refill_addr = addr

    def enen(self):
        return self.refill_in_fly

    @def_method_mock(lambda self: self.m.refiller.accept_refill_mock, enable=enen)
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
            "addr": addr,
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
        await self.m.issue_req.call(sim, addr=addr)

    async def expect_resp(self, sim: TestbenchContext, wait=False):
        if wait:
            *_, resp = await self.m.accept_res.sample_outputs_until_done(sim)
        else:
            *_, resp = await self.m.accept_res.sample_outputs(sim)

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
        self.m.accept_res.enable(sim)
        await self.expect_resp(sim, wait=True)
        self.m.accept_res.disable(sim)

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
            self.m.accept_res.enable(sim)
            for i in range(0, self.cp.num_of_sets * self.cp.line_size_bytes, 4):
                addr = 0x00010000 + i
                self.issued_requests.append(addr)

                # Send the request
                ret = await self.m.issue_req.call_try(sim, addr=addr)
                assert ret is not None

                # After a cycle the response should be ready
                await self.expect_resp(sim)

            self.m.accept_res.disable(sim)

            await self.tick(sim, 4)

            # Check how the cache handles queuing the requests
            await self.send_req(sim, addr=0x00010000 + 3 * self.cp.line_size_bytes)
            await self.send_req(sim, addr=0x00010004)

            # Wait a few cycles. There are two requests queued
            await self.tick(sim, 4)

            self.m.accept_res.enable(sim)
            await self.expect_resp(
                sim,
            )
            await self.expect_resp(
                sim,
            )
            await self.send_req(sim, addr=0x0001000C)
            await self.expect_resp(
                sim,
            )

            self.m.accept_res.disable(sim)

            await self.tick(sim, 4)

            # Schedule two requests, the first one causing a cache miss
            await self.send_req(sim, addr=0x00020000)
            await self.send_req(sim, addr=0x00010000 + self.cp.line_size_bytes)

            self.m.accept_res.enable(sim)

            await self.expect_resp(sim, wait=True)
            await self.expect_resp(
                sim,
            )
            self.m.accept_res.disable(sim)

            await self.tick(sim, 2)

            # Schedule two requests, the second one causing a cache miss
            await self.send_req(sim, addr=0x00020004)
            await self.send_req(sim, addr=0x00030000 + self.cp.line_size_bytes)

            self.m.accept_res.enable(sim)

            await self.expect_resp(
                sim,
            )
            await self.expect_resp(sim, wait=True)
            self.m.accept_res.disable(sim)

            await self.tick(sim, 2)

            # Schedule two requests, both causing a cache miss
            await self.send_req(sim, addr=0x00040000)
            await self.send_req(sim, addr=0x00050000 + self.cp.line_size_bytes)

            self.m.accept_res.enable(sim)

            await self.expect_resp(sim, wait=True)
            await self.expect_resp(sim, wait=True)
            self.m.accept_res.disable(sim)

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

            await self.m.flush_cache.call(sim)

            # The cache should be empty
            for s in range(self.cp.num_of_sets):
                for w in range(self.cp.num_of_ways):
                    addr = w * 0x00010000 + s * self.cp.line_size_bytes
                    await self.call_cache(sim, addr)
                    self.expect_refill(addr)

            # Try to flush during refilling the line
            await self.send_req(sim, 0x00030000)
            await self.m.flush_cache.call(sim)
            # We still should be able to accept the response for the last request
            self.assert_resp(await self.m.accept_res.call(sim))
            self.expect_refill(0x00030000)

            await self.call_cache(sim, 0x00010000)
            self.expect_refill(0x00010000)

            # Try to execute issue_req and flush_cache methods at the same time
            self.issued_requests.append(0x00010000)
            issue_req_res, flush_cache_res = (
                await CallTrigger(sim).call(self.m.issue_req, addr=0x00010000).call(self.m.flush_cache)
            )
            assert issue_req_res is None
            assert flush_cache_res is not None
            await self.m.issue_req.call(sim, addr=0x00010000)
            self.assert_resp(await self.m.accept_res.call(sim))
            self.expect_refill(0x00010000)

            # Schedule two requests and then flush
            await self.send_req(sim, 0x00000000 + self.cp.line_size_bytes)
            await self.send_req(sim, 0x00010000)

            res = await self.m.flush_cache.call_try(sim)
            # We cannot flush until there are two pending requests
            assert res is None
            res = await self.m.flush_cache.call_try(sim)
            assert res is None

            # Accept the first response
            self.assert_resp(await self.m.accept_res.call(sim))

            await self.m.flush_cache.call(sim)

            # And accept the second response ensuring that we got old data
            self.assert_resp(await self.m.accept_res.call(sim))
            self.expect_refill(0x00000000 + self.cp.line_size_bytes)

            # Just make sure that the line is truly flushed
            await self.call_cache(sim, 0x00010000)
            self.expect_refill(0x00010000)

        with self.run_simulation(self.m) as sim:
            sim.add_testbench(cache_process)

    def test_errors(self):
        self.init_module(1, 4)

        async def cache_process(sim: TestbenchContext):
            self.add_bad_addr(0x00010000)  # Bad addr at the beggining of the line
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

            self.m.accept_res.disable(sim)

            # Schedule two requests, the first one causing an error
            await self.send_req(sim, addr=0x00020000)
            await self.send_req(sim, addr=0x00011000)

            self.m.accept_res.enable(sim)

            await self.expect_resp(sim, wait=True)
            await self.expect_resp(sim, wait=True)
            self.m.accept_res.disable(sim)

            await self.tick(sim, 3)

            # Schedule two requests, the second one causing an error
            await self.send_req(sim, addr=0x00021004)
            await self.send_req(sim, addr=0x00030000)

            await self.tick(sim, 10)

            self.m.accept_res.enable(sim)

            await self.expect_resp(sim, wait=True)
            await self.expect_resp(sim, wait=True)
            self.m.accept_res.disable(sim)

            await self.tick(sim, 3)

            # Schedule two requests, both causing an error
            await self.send_req(sim, addr=0x00020000)
            await self.send_req(sim, addr=0x00010000)

            self.m.accept_res.enable(sim)

            await self.expect_resp(sim, wait=True)
            await self.expect_resp(sim, wait=True)
            self.m.accept_res.disable(sim)

            # The second request will cause an error
            await self.send_req(sim, addr=0x00021004)
            await self.send_req(sim, addr=0x00030000)

            await self.tick(sim, 10)

            # Accept the first response
            self.m.accept_res.enable(sim)
            await self.expect_resp(sim, wait=True)

            # Wait before accepting the second response
            self.m.accept_res.disable(sim)
            await self.tick(sim, 10)
            self.m.accept_res.enable(sim)
            await self.expect_resp(sim, wait=True)

            # This request should not cause an error
            await self.send_req(sim, addr=0x00011000)
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

                self.assert_resp(await self.m.accept_res.call(sim))
                await self.random_wait_geom(sim, 0.2)

        with self.run_simulation(self.m) as sim:
            sim.add_testbench(sender)
            sim.add_testbench(receiver)
            sim.add_testbench(refiller_ctrl, background=True)
