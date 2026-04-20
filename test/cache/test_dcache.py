from collections import deque

from amaranth import Elaboratable
from amaranth.utils import exact_log2

from transactron.lib import Adapter, AdapterTrans
from transactron.testing import TestCaseWithSimulator, TestbenchIO, def_method_mock, TestbenchContext
from transactron.testing.method_mock import MethodMock
from transactron.utils import ModuleConnector

from coreblocks.cache.dcache import DCache
from coreblocks.cache.iface import DataCacheRefillerInterface
from coreblocks.interface.layouts import DCacheLayouts
from coreblocks.params import GenParams
from coreblocks.params.configurations import test_core_config


class MockedDataCacheRefiller(Elaboratable, DataCacheRefillerInterface):
    def __init__(self, gen_params: GenParams):
        layouts = gen_params.get(DCacheLayouts)

        self.start_refill_mock = TestbenchIO(Adapter(i=layouts.start_refill))
        self.accept_refill_mock = TestbenchIO(Adapter(o=layouts.accept_refill))
        self.start_writeback_mock = TestbenchIO(Adapter(i=layouts.start_writeback))
        self.accept_writeback_mock = TestbenchIO(Adapter(o=layouts.accept_writeback))

        self.start_refill = self.start_refill_mock.adapter.iface
        self.accept_refill = self.accept_refill_mock.adapter.iface
        self.start_writeback = self.start_writeback_mock.adapter.iface
        self.accept_writeback = self.accept_writeback_mock.adapter.iface

    def elaborate(self, platform):
        return ModuleConnector(
            start_refill=self.start_refill_mock,
            accept_refill=self.accept_refill_mock,
            start_writeback=self.start_writeback_mock,
            accept_writeback=self.accept_writeback_mock,
        )


class DCacheTestCircuit(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params
        self.cp = self.gen_params.dcache_params

    def elaborate(self, platform):
        self.refiller = MockedDataCacheRefiller(self.gen_params)
        self.cache = DCache(self.gen_params.get(DCacheLayouts), self.cp, self.refiller)
        self.issue_req = TestbenchIO(AdapterTrans.create(self.cache.issue_req))
        self.accept_res = TestbenchIO(AdapterTrans.create(self.cache.accept_res))
        self.flush_cache = TestbenchIO(AdapterTrans.create(self.cache.flush))

        return ModuleConnector(
            refiller=self.refiller,
            cache=self.cache,
            issue_req=self.issue_req,
            accept_res=self.accept_res,
            flush_cache=self.flush_cache,
        )


class TestDCache(TestCaseWithSimulator):
    def setup_method(self) -> None:
        self.gen_params = GenParams(
            test_core_config.replace(
                xlen=32,
                dcache_ways=2,
                dcache_sets_bits=2,
                dcache_line_bytes_log=4,
            )
        )
        self.cp = self.gen_params.dcache_params
        self.m = DCacheTestCircuit(self.gen_params)
        self.refill_start_calls = deque()
        self.refill_responses = deque()

    @def_method_mock(lambda self: self.m.refiller.start_refill_mock, enable=lambda self: True)
    def start_refill_unexpected(self, addr):
        @MethodMock.effect
        def eff():
            self.refill_start_calls.append(addr)
            if not self.refill_responses:
                self.refill_responses.append({"addr": addr, "data": 0, "error": 1, "last": 1})

    @def_method_mock(lambda self: self.m.refiller.accept_refill_mock, enable=lambda self: True)
    def accept_refill_unexpected(self):
        @MethodMock.effect
        def eff():
            if not self.refill_responses:
                raise AssertionError("unexpected accept_refill call")
            self.refill_responses.popleft()

        if self.refill_responses:
            return self.refill_responses[0]
        return {"addr": 0, "data": 0, "error": 0, "last": 1}

    @def_method_mock(lambda self: self.m.refiller.start_writeback_mock, enable=lambda self: True)
    def start_writeback_unexpected(self, addr):
        @MethodMock.effect
        def eff():
            raise AssertionError(f"unexpected start_writeback call for address 0x{addr:08x}")

    @def_method_mock(lambda self: self.m.refiller.accept_writeback_mock, enable=lambda self: True)
    def accept_writeback_unexpected(self):
        @MethodMock.effect
        def eff():
            raise AssertionError("unexpected accept_writeback call")

        return {"error": 0}

    def split_addr(self, addr: int) -> tuple[int, int, int]:
        index = (addr >> self.cp.offset_bits) & (self.cp.num_of_sets - 1)
        tag = addr >> (self.cp.offset_bits + self.cp.index_bits)
        word_offset = (addr & (self.cp.line_size_bytes - 1)) >> exact_log2(self.cp.word_width_bytes)
        return tag, index, word_offset

    def encode_tag_entry(self, *, valid: int, dirty: int, tag: int) -> dict[str, int]:
        return {"valid": valid, "dirty": dirty, "tag": tag}

    def line_word_addr(self, index: int, word_offset: int) -> int:
        return (index << exact_log2(self.cp.words_in_line)) | word_offset

    def merge_word(self, initial: int, new: int, byte_mask: int) -> int:
        result = initial
        for byte in range(self.cp.word_width_bytes):
            if byte_mask & (1 << byte):
                byte_shift = byte * 8
                result &= ~(0xFF << byte_shift)
                result |= ((new >> byte_shift) & 0xFF) << byte_shift
        return result

    async def wait_for_initial_flush(self, sim: TestbenchContext):
        for _ in range(self.cp.num_of_sets * 3 + 4):
            await sim.tick()

    async def preload_line(
        self, sim: TestbenchContext, addr_base: int, words: list[int], *, way: int = 0, dirty: int = 0
    ):
        tag, index, _ = self.split_addr(addr_base)
        sim.set(
            self.m.cache.mem.tag_mems[way].data[index],  # type: ignore[arg-type]
            self.encode_tag_entry(valid=1, dirty=dirty, tag=tag),
        )

        for word_offset, word in enumerate(words):
            mem_addr = self.line_word_addr(index, word_offset)
            sim.set(self.m.cache.mem.data_mems[way].data[mem_addr], word)  # type: ignore[arg-type]

        await sim.tick()

    async def call_cache(self, sim: TestbenchContext, *, addr: int, data: int = 0, byte_mask: int = 0, store: int = 0):
        await self.m.issue_req.call(sim, addr=addr, data=data, byte_mask=byte_mask, store=store)
        return await self.m.accept_res.call(sim)

    def queue_refill_line(self, line_addr: int, words: list[int], *, error: int = 0):
        for i, word in enumerate(words):
            self.refill_responses.append(
                {
                    "addr": line_addr + i * self.cp.word_width_bytes,
                    "data": word,
                    "error": error,
                    "last": int(i == len(words) - 1 or error),
                }
            )
            if error:
                break

    def read_tag_entry(self, sim: TestbenchContext, *, way: int, index: int) -> dict[str, int]:
        raw_tag = sim.get(self.m.cache.mem.tag_mems[way].data[index])  # type: ignore[arg-type]
        return {
            "valid": raw_tag["valid"],
            "dirty": raw_tag["dirty"],
            "tag": raw_tag["tag"],
        }

    def read_data_word(self, sim: TestbenchContext, *, way: int, index: int, word_offset: int) -> int:
        mem_addr = self.line_word_addr(index, word_offset)
        return sim.get(self.m.cache.mem.data_mems[way].data[mem_addr])  # type: ignore[arg-type]

    def test_initial_miss_returns_error(self):
        async def cache_process(sim: TestbenchContext):
            await self.wait_for_initial_flush(sim)

            resp = await self.call_cache(sim, addr=0x00000100)

            assert resp["error"] == 1
            assert resp["data"] == 0

        with self.run_simulation(self.m) as sim:
            sim.add_testbench(cache_process)

    def test_load_hit_returns_cached_word(self):
        async def cache_process(sim: TestbenchContext):
            base_addr = 0x00000120
            words = [0x11223344, 0x55667788, 0x99AABBCC, 0xDDEEFF00]

            await self.wait_for_initial_flush(sim)
            await self.preload_line(sim, base_addr, words, way=0, dirty=0)

            resp = await self.call_cache(sim, addr=base_addr + self.cp.word_width_bytes)

            assert resp["error"] == 0
            assert resp["data"] == words[1]

        with self.run_simulation(self.m) as sim:
            sim.add_testbench(cache_process)

    def test_store_hit_updates_word_and_sets_dirty(self):
        async def cache_process(sim: TestbenchContext):
            base_addr = 0x00000140
            initial_words = [0x11223344, 0x55667788, 0x99AABBCC, 0xDDEEFF00]
            store_addr = base_addr + self.cp.word_width_bytes
            store_data = 0xAABBCCDD
            byte_mask = 0b0101

            await self.wait_for_initial_flush(sim)
            await self.preload_line(sim, base_addr, initial_words, way=0, dirty=0)

            resp = await self.call_cache(sim, addr=store_addr, data=store_data, byte_mask=byte_mask, store=1)

            assert resp["error"] == 0
            assert resp["data"] == 0

            await sim.tick()

            tag, index, word_offset = self.split_addr(store_addr)
            expected_word = self.merge_word(initial_words[1], store_data, byte_mask)

            stored_word = self.read_data_word(sim, way=0, index=index, word_offset=word_offset)
            stored_tag = self.read_tag_entry(sim, way=0, index=index)

            assert stored_word == expected_word
            assert stored_tag["valid"] == 1
            assert stored_tag["dirty"] == 1
            assert stored_tag["tag"] == tag

            load_resp = await self.call_cache(sim, addr=store_addr)
            assert load_resp["error"] == 0
            assert load_resp["data"] == expected_word

        with self.run_simulation(self.m) as sim:
            sim.add_testbench(cache_process)

    def test_second_request_not_accepted_while_response_pending(self):
        async def cache_process(sim: TestbenchContext):
            base_addr = 0x00000180
            words = [0x01020304, 0x11121314, 0x21222324, 0x31323334]

            await self.wait_for_initial_flush(sim)
            await self.preload_line(sim, base_addr, words, way=0, dirty=0)

            await self.m.issue_req.call(sim, addr=base_addr, data=0, byte_mask=0, store=0)

            ret = await self.m.issue_req.call_try(
                sim, addr=base_addr + self.cp.word_width_bytes, data=0, byte_mask=0, store=0
            )
            assert ret is None

            first_resp = await self.m.accept_res.call(sim)
            assert first_resp["error"] == 0
            assert first_resp["data"] == words[0]

            second_resp = await self.call_cache(sim, addr=base_addr + self.cp.word_width_bytes)
            assert second_resp["error"] == 0
            assert second_resp["data"] == words[1]

        with self.run_simulation(self.m) as sim:
            sim.add_testbench(cache_process)

    def test_flush_invalidates_clean_line(self):
        async def cache_process(sim: TestbenchContext):
            base_addr = 0x000001C0
            words = [0xCAFEBABE, 0x0BADF00D, 0x12345678, 0x89ABCDEF]

            await self.wait_for_initial_flush(sim)
            await self.preload_line(sim, base_addr, words, way=0, dirty=0)

            hit_resp = await self.call_cache(sim, addr=base_addr)
            assert hit_resp["error"] == 0
            assert hit_resp["data"] == words[0]

            await self.m.flush_cache.call(sim)
            await self.wait_for_initial_flush(sim)

            miss_resp = await self.call_cache(sim, addr=base_addr)
            assert miss_resp["error"] == 1
            assert miss_resp["data"] == 0

        with self.run_simulation(self.m) as sim:
            sim.add_testbench(cache_process)

    def test_load_clean_miss_refills_line_and_replays_request(self):
        async def cache_process(sim: TestbenchContext):
            base_addr = 0x00000200
            words = [0xAAAABBBB, 0xCCCCDDDD, 0x11112222, 0x33334444]

            await self.wait_for_initial_flush(sim)
            self.queue_refill_line(base_addr, words)

            resp = await self.call_cache(sim, addr=base_addr + self.cp.word_width_bytes)

            assert list(self.refill_start_calls) == [base_addr]
            assert resp["error"] == 0
            assert resp["data"] == words[1]
            assert not self.refill_responses

            hit_resp = await self.call_cache(sim, addr=base_addr + 2 * self.cp.word_width_bytes)
            assert hit_resp["error"] == 0
            assert hit_resp["data"] == words[2]
            assert list(self.refill_start_calls) == [base_addr]

        with self.run_simulation(self.m) as sim:
            sim.add_testbench(cache_process)

    def test_store_clean_miss_refills_then_updates_line(self):
        async def cache_process(sim: TestbenchContext):
            base_addr = 0x00000240
            initial_words = [0x10203040, 0x50607080, 0x90A0B0C0, 0xD0E0F000]
            store_addr = base_addr + self.cp.word_width_bytes
            store_data = 0x11223344
            byte_mask = 0b0011

            await self.wait_for_initial_flush(sim)
            self.queue_refill_line(base_addr, initial_words)

            resp = await self.call_cache(sim, addr=store_addr, data=store_data, byte_mask=byte_mask, store=1)

            assert list(self.refill_start_calls) == [base_addr]
            assert resp["error"] == 0
            assert resp["data"] == 0
            assert not self.refill_responses

            await sim.tick()

            tag, index, word_offset = self.split_addr(store_addr)
            expected_word = self.merge_word(initial_words[1], store_data, byte_mask)
            stored_word = self.read_data_word(sim, way=0, index=index, word_offset=word_offset)
            stored_tag = self.read_tag_entry(sim, way=0, index=index)

            assert stored_word == expected_word
            assert stored_tag["valid"] == 1
            assert stored_tag["dirty"] == 1
            assert stored_tag["tag"] == tag

        with self.run_simulation(self.m) as sim:
            sim.add_testbench(cache_process)
