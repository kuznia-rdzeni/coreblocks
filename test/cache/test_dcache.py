from collections import deque

from amaranth import Elaboratable
from amaranth.utils import exact_log2

from transactron.lib import Adapter, AdapterTrans
from transactron.testing import TestCaseWithSimulator, TestbenchIO, def_method_mock, TestbenchContext
from transactron.testing.method_mock import MethodMock
from transactron.utils import ModuleConnector

from coreblocks.cache.dcache import DCache
from coreblocks.cache.refiller import SimpleCommonBusDataCacheRefiller
from coreblocks.cache.iface import DataCacheRefillerInterface
from coreblocks.interface.layouts import DCacheLayouts
from coreblocks.params import GenParams
from coreblocks.params.configurations import test_core_config

from ..peripherals.bus_mock import BusMockParameters, MockMasterAdapter


class SimpleCommonBusDataCacheRefillerTestCircuit(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params
        self.cp = self.gen_params.dcache_params

    def elaborate(self, platform):
        layouts = self.gen_params.get(DCacheLayouts)
        bus_mock_params = BusMockParameters(
            data_width=self.gen_params.isa.xlen,
            addr_width=self.gen_params.wb_params.addr_width,
        )

        self.bus_master_adapter = MockMasterAdapter(bus_mock_params)
        self.refiller = SimpleCommonBusDataCacheRefiller(layouts, self.cp, self.bus_master_adapter)

        self.writeback_data_mock = TestbenchIO(Adapter(o=layouts.provide_writeback_data))
        self.refiller.get_writeback_data.provide(self.writeback_data_mock.adapter.iface)

        self.start_refill = TestbenchIO(AdapterTrans.create(self.refiller.start_refill))
        self.accept_refill = TestbenchIO(AdapterTrans.create(self.refiller.accept_refill))
        self.start_writeback = TestbenchIO(AdapterTrans.create(self.refiller.start_writeback))
        self.accept_writeback = TestbenchIO(AdapterTrans.create(self.refiller.accept_writeback))

        return ModuleConnector(
            bus_master_adapter=self.bus_master_adapter,
            refiller=self.refiller,
            writeback_data_mock=self.writeback_data_mock,
            start_refill=self.start_refill,
            accept_refill=self.accept_refill,
            start_writeback=self.start_writeback,
            accept_writeback=self.accept_writeback,
        )


class TestSimpleCommonBusDataCacheRefiller(TestCaseWithSimulator):
    def setup_method(self) -> None:
        self.gen_params = GenParams(
            test_core_config.replace(
                xlen=32,
                dcache_line_bytes_log=4,
            )
        )
        self.cp = self.gen_params.dcache_params
        self.m = SimpleCommonBusDataCacheRefillerTestCircuit(self.gen_params)
        self.writeback_words = deque()

    @def_method_mock(lambda self: self.m.writeback_data_mock, enable=lambda self: bool(self.writeback_words))
    def writeback_data(self):
        @MethodMock.effect
        def eff():
            self.writeback_words.popleft()

        return {"data": self.writeback_words[0]}

    def bus_word_addr(self, byte_addr: int, word_idx: int) -> int:
        return (byte_addr >> exact_log2(self.cp.word_width_bytes)) + word_idx

    def byte_word_addr(self, byte_addr: int, word_idx: int) -> int:
        return byte_addr + word_idx * self.cp.word_width_bytes

    def full_sel(self) -> int:
        return (1 << self.cp.word_width_bytes) - 1

    def test_refill_reads_full_line_and_emits_word_beats(self):
        async def process(sim: TestbenchContext):
            base_addr = 0x00000100
            words = [0x10203040, 0x50607080, 0x90A0B0C0, 0xD0E0F000]

            await self.m.start_refill.call(sim, addr=base_addr)

            for word_idx, word in enumerate(words):
                req = await self.m.bus_master_adapter.request_read_mock.call(sim)
                assert req["addr"] == self.bus_word_addr(base_addr, word_idx)
                assert req["sel"] == self.full_sel()

                await self.m.bus_master_adapter.get_read_response_mock.call(sim, data=word, err=0)
                resp = await self.m.accept_refill.call(sim)

                assert resp["addr"] == self.byte_word_addr(base_addr, word_idx)
                assert resp["data"] == word
                assert resp["error"] == 0
                assert resp["last"] == int(word_idx == len(words) - 1)

        with self.run_simulation(self.m) as sim:
            sim.add_testbench(process)

    def test_refill_error_returns_error_last_and_stops(self):
        async def process(sim: TestbenchContext):
            base_addr = 0x00000140
            words = [0x11111111, 0x22222222]

            await self.m.start_refill.call(sim, addr=base_addr)

            req = await self.m.bus_master_adapter.request_read_mock.call(sim)
            assert req["addr"] == self.bus_word_addr(base_addr, 0)
            await self.m.bus_master_adapter.get_read_response_mock.call(sim, data=words[0], err=0)

            resp = await self.m.accept_refill.call(sim)
            assert resp["addr"] == self.byte_word_addr(base_addr, 0)
            assert resp["data"] == words[0]
            assert resp["error"] == 0
            assert resp["last"] == 0

            req = await self.m.bus_master_adapter.request_read_mock.call(sim)
            assert req["addr"] == self.bus_word_addr(base_addr, 1)
            await self.m.bus_master_adapter.get_read_response_mock.call(sim, data=words[1], err=1)

            resp = await self.m.accept_refill.call(sim)
            assert resp["addr"] == self.byte_word_addr(base_addr, 1)
            assert resp["data"] == words[1]
            assert resp["error"] == 1
            assert resp["last"] == 1

            for _ in range(3):
                req = await self.m.bus_master_adapter.request_read_mock.call_try(sim)
                assert req is None

        with self.run_simulation(self.m) as sim:
            sim.add_testbench(process)

    def test_writeback_writes_full_line_and_returns_success(self):
        async def process(sim: TestbenchContext):
            base_addr = 0x00000200
            words = [0xDEADBEEF, 0x11223344, 0x55667788, 0x99AABBCC]
            self.writeback_words.extend(words)

            await self.m.start_writeback.call(sim, addr=base_addr)

            for word_idx, word in enumerate(words):
                req = await self.m.bus_master_adapter.request_write_mock.call(sim)
                assert req["addr"] == self.bus_word_addr(base_addr, word_idx)
                assert req["data"] == word
                assert req["sel"] == self.full_sel()

                await self.m.bus_master_adapter.get_write_response_mock.call(sim, err=0)

            resp = await self.m.accept_writeback.call(sim)
            assert resp["error"] == 0
            assert not self.writeback_words

        with self.run_simulation(self.m) as sim:
            sim.add_testbench(process)

    def test_writeback_accumulates_error(self):
        async def process(sim: TestbenchContext):
            base_addr = 0x00000240
            words = [0x01020304, 0x11121314, 0x21222324, 0x31323334]
            errors = [0, 1, 0, 0]
            self.writeback_words.extend(words)

            await self.m.start_writeback.call(sim, addr=base_addr)

            for word_idx, word in enumerate(words):
                req = await self.m.bus_master_adapter.request_write_mock.call(sim)
                assert req["addr"] == self.bus_word_addr(base_addr, word_idx)
                assert req["data"] == word

                await self.m.bus_master_adapter.get_write_response_mock.call(sim, err=errors[word_idx])

            resp = await self.m.accept_writeback.call(sim)
            assert resp["error"] == 1
            assert not self.writeback_words

        with self.run_simulation(self.m) as sim:
            sim.add_testbench(process)

    def test_start_methods_are_not_ready_while_busy(self):
        async def process(sim: TestbenchContext):
            refill_addr = 0x00000300
            writeback_addr = 0x00000340
            words = [0xA0A0A0A0, 0xB1B1B1B1, 0xC2C2C2C2, 0xD3D3D3D3]

            await self.m.start_refill.call(sim, addr=refill_addr)
            ret = await self.m.start_writeback.call_try(sim, addr=writeback_addr)
            assert ret is None

            for word_idx, word in enumerate(words):
                await self.m.bus_master_adapter.request_read_mock.call(sim)
                await self.m.bus_master_adapter.get_read_response_mock.call(sim, data=word, err=0)
                resp = await self.m.accept_refill.call(sim)
                assert resp["last"] == int(word_idx == len(words) - 1)

            self.writeback_words.extend(words)
            await self.m.start_writeback.call(sim, addr=writeback_addr)
            ret = await self.m.start_refill.call_try(sim, addr=refill_addr)
            assert ret is None

            for _ in words:
                await self.m.bus_master_adapter.request_write_mock.call(sim)
                await self.m.bus_master_adapter.get_write_response_mock.call(sim, err=0)

            resp = await self.m.accept_writeback.call(sim)
            assert resp["error"] == 0

            ret = await self.m.start_refill.call_try(sim, addr=refill_addr)
            assert ret is not None

        with self.run_simulation(self.m) as sim:
            sim.add_testbench(process)


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
        self.provide_writeback_data = TestbenchIO(AdapterTrans.create(self.cache.provide_writeback_data))

        return ModuleConnector(
            refiller=self.refiller,
            cache=self.cache,
            issue_req=self.issue_req,
            accept_res=self.accept_res,
            flush_cache=self.flush_cache,
            provide_writeback_data=self.provide_writeback_data,
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
        self.writeback_start_calls = deque()
        self.writeback_accept_responses = deque()
        self.allow_writeback_accept = False

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
            self.writeback_start_calls.append(addr)

    @def_method_mock(
        lambda self: self.m.refiller.accept_writeback_mock,
        enable=lambda self: self.allow_writeback_accept and bool(self.writeback_accept_responses),
    )
    def accept_writeback_unexpected(self):
        @MethodMock.effect
        def eff():
            if not self.writeback_accept_responses:
                raise AssertionError("unexpected accept_writeback call")
            self.writeback_accept_responses.popleft()

        return self.writeback_accept_responses[0]

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

    async def wait_for_flush(self, sim: TestbenchContext):
        for _ in range(self.cp.num_of_sets * 3 + 4):
            await sim.tick()

    async def load_line_directly(
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

    async def collect_writeback_line(self, sim: TestbenchContext, *, words_in_line: int) -> list[int]:
        words = []
        await sim.tick()
        for _ in range(words_in_line):
            resp = await self.m.provide_writeback_data.call(sim)
            words.append(resp["data"])
            await sim.tick()
        return words

    async def wait_until(self, sim: TestbenchContext, pred, *, max_ticks: int = 50):
        for _ in range(max_ticks):
            if pred():
                return
            await sim.tick()
        raise AssertionError("condition not met in time")

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

    def same_set_addr(self, addr: int, distance: int) -> int:
        return addr + distance * self.cp.num_of_sets * self.cp.line_size_bytes

    def test_miss_returns_error_on_empty_refiller(self):
        async def cache_process(sim: TestbenchContext):
            await self.wait_for_flush(sim)

            resp = await self.call_cache(sim, addr=0x00000100)

            assert resp["error"] == 1
            assert resp["data"] == 0

        with self.run_simulation(self.m) as sim:
            sim.add_testbench(cache_process)

    def test_load_hit(self):
        async def cache_process(sim: TestbenchContext):
            base_addr = 0x00000120
            words = [0x11223344, 0x55667788, 0x99AABBCC, 0xDDEEFF00]

            await self.wait_for_flush(sim)
            await self.load_line_directly(sim, base_addr, words, way=0, dirty=0)

            resp = await self.call_cache(sim, addr=base_addr + self.cp.word_width_bytes)

            assert resp["error"] == 0
            assert resp["data"] == words[1]

        with self.run_simulation(self.m) as sim:
            sim.add_testbench(cache_process)

    def test_store_hit(self):
        async def cache_process(sim: TestbenchContext):
            base_addr = 0x00000140
            initial_words = [0x11223344, 0x55667788, 0x99AABBCC, 0xDDEEFF00]
            store_addr = base_addr + self.cp.word_width_bytes
            store_data = 0xAABBCCDD
            byte_mask = 0b0101

            await self.wait_for_flush(sim)
            await self.load_line_directly(sim, base_addr, initial_words, way=0, dirty=0)

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

            await self.wait_for_flush(sim)
            await self.load_line_directly(sim, base_addr, words, way=0, dirty=0)

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

    def test_flush_invalidates(self):
        async def cache_process(sim: TestbenchContext):
            base_addr = 0x000001C0
            words = [0xCAFEBABE, 0x0BADF00D, 0x12345678, 0x89ABCDEF]

            await self.wait_for_flush(sim)
            await self.load_line_directly(sim, base_addr, words, way=0, dirty=0)

            hit_resp = await self.call_cache(sim, addr=base_addr)
            assert hit_resp["error"] == 0
            assert hit_resp["data"] == words[0]

            await self.m.flush_cache.call(sim)
            await self.wait_for_flush(sim)

            miss_resp = await self.call_cache(sim, addr=base_addr)
            assert miss_resp["error"] == 1
            assert miss_resp["data"] == 0

        with self.run_simulation(self.m) as sim:
            sim.add_testbench(cache_process)

    def test_load_miss(self):
        async def cache_process(sim: TestbenchContext):
            base_addr = 0x00000200
            words = [0xAAAABBBB, 0xCCCCDDDD, 0x11112222, 0x33334444]

            await self.wait_for_flush(sim)
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

    def test_store_miss(self):
        async def cache_process(sim: TestbenchContext):
            base_addr = 0x00000240
            initial_words = [0x10203040, 0x50607080, 0x90A0B0C0, 0xD0E0F000]
            store_addr = base_addr + self.cp.word_width_bytes
            store_data = 0x11223344
            byte_mask = 0b0011

            await self.wait_for_flush(sim)
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

    def test_refill_error(self):
        async def cache_process(sim: TestbenchContext):
            base_addr = 0x00000280
            words = [0xABCDEF01, 0x23456789, 0x3456789A, 0x456789AB]

            await self.wait_for_flush(sim)
            self.queue_refill_line(base_addr, words, error=1)

            resp = await self.call_cache(sim, addr=base_addr)

            assert list(self.refill_start_calls) == [base_addr]
            assert resp["error"] == 1
            assert resp["data"] == 0
            assert not self.refill_responses

            _, index, _ = self.split_addr(base_addr)
            way0_entry = self.read_tag_entry(sim, way=0, index=index)
            way1_entry = self.read_tag_entry(sim, way=1, index=index)

            assert way0_entry["valid"] == 0
            assert way1_entry["valid"] == 0
            assert not self.writeback_start_calls

        with self.run_simulation(self.m) as sim:
            sim.add_testbench(cache_process)

    def test_load_miss_multiple_lines(self):
        async def cache_process(sim: TestbenchContext):
            old_base_addr = 0x00000100
            old_words = [0xDEADBEEF, 0x11223344, 0x55667788, 0x99AABBCC]
            other_base_addr = 0x00000140
            other_words = [0x01020304, 0x11121314, 0x21222324, 0x31323334]
            new_base_addr = 0x00000200
            new_words = [0xAAAABBBB, 0xCCCCDDDD, 0xEEEEFFFF, 0x12345678]

            await self.wait_for_flush(sim)
            await self.load_line_directly(sim, old_base_addr, old_words, way=0, dirty=1)
            await self.load_line_directly(sim, other_base_addr, other_words, way=1, dirty=0)
            self.queue_refill_line(new_base_addr, new_words)
            self.writeback_accept_responses.append({"error": 0})

            await self.m.issue_req.call(
                sim, addr=new_base_addr + self.cp.word_width_bytes, data=0, byte_mask=0, store=0
            )

            await self.wait_until(sim, lambda: len(self.writeback_start_calls) == 1)
            assert list(self.writeback_start_calls) == [old_base_addr]
            assert not self.refill_start_calls

            written_back_words = await self.collect_writeback_line(sim, words_in_line=self.cp.words_in_line)
            assert written_back_words == old_words
            assert not self.refill_start_calls

            self.allow_writeback_accept = True
            resp = await self.m.accept_res.call(sim)

            assert list(self.refill_start_calls) == [new_base_addr]
            assert resp["error"] == 0
            assert resp["data"] == new_words[1]
            assert not self.refill_responses

            _, index, _ = self.split_addr(new_base_addr)
            new_tag, _, _ = self.split_addr(new_base_addr)
            stored_tag = self.read_tag_entry(sim, way=0, index=index)
            hit_resp = await self.call_cache(sim, addr=new_base_addr + 2 * self.cp.word_width_bytes)

            assert stored_tag["valid"] == 1
            assert stored_tag["tag"] == new_tag
            assert hit_resp["error"] == 0
            assert hit_resp["data"] == new_words[2]

        with self.run_simulation(self.m) as sim:
            sim.add_testbench(cache_process)

    def test_store_miss_multiple_lines(self):
        async def cache_process(sim: TestbenchContext):
            old_base_addr = 0x00000140
            old_words = [0xCAFEBABE, 0x0BADF00D, 0x01020304, 0xA0B0C0D0]
            other_base_addr = 0x00000100
            other_words = [0xDEADBEEF, 0x11223344, 0x55667788, 0x99AABBCC]
            new_base_addr = 0x00000240
            new_words = [0x10203040, 0x50607080, 0x90A0B0C0, 0xD0E0F000]
            store_addr = new_base_addr + self.cp.word_width_bytes
            store_data = 0x11223344
            byte_mask = 0b0011

            await self.wait_for_flush(sim)
            await self.load_line_directly(sim, old_base_addr, old_words, way=0, dirty=1)
            await self.load_line_directly(sim, other_base_addr, other_words, way=1, dirty=0)
            self.queue_refill_line(new_base_addr, new_words)
            self.writeback_accept_responses.append({"error": 0})

            await self.m.issue_req.call(sim, addr=store_addr, data=store_data, byte_mask=byte_mask, store=1)

            await self.wait_until(sim, lambda: len(self.writeback_start_calls) == 1)
            assert list(self.writeback_start_calls) == [old_base_addr]
            assert not self.refill_start_calls

            written_back_words = await self.collect_writeback_line(sim, words_in_line=self.cp.words_in_line)
            assert written_back_words == old_words
            assert not self.refill_start_calls

            self.allow_writeback_accept = True
            resp = await self.m.accept_res.call(sim)

            assert list(self.refill_start_calls) == [new_base_addr]
            assert resp["error"] == 0
            assert resp["data"] == 0
            assert not self.refill_responses

            await sim.tick()

            new_tag, index, word_offset = self.split_addr(store_addr)
            expected_word = self.merge_word(new_words[1], store_data, byte_mask)
            stored_word = self.read_data_word(sim, way=0, index=index, word_offset=word_offset)
            stored_tag = self.read_tag_entry(sim, way=0, index=index)

            assert stored_word == expected_word
            assert stored_tag["valid"] == 1
            assert stored_tag["dirty"] == 1
            assert stored_tag["tag"] == new_tag

        with self.run_simulation(self.m) as sim:
            sim.add_testbench(cache_process)

    def test_miss_writeback_error(self):
        async def cache_process(sim: TestbenchContext):
            old_base_addr = 0x00000100
            old_words = [0xDEADBEEF, 0x11223344, 0x55667788, 0x99AABBCC]
            other_base_addr = 0x00000140
            other_words = [0x01020304, 0x11121314, 0x21222324, 0x31323334]
            new_base_addr = 0x00000200

            await self.wait_for_flush(sim)
            await self.load_line_directly(sim, old_base_addr, old_words, way=0, dirty=1)
            await self.load_line_directly(sim, other_base_addr, other_words, way=1, dirty=0)
            self.writeback_accept_responses.append({"error": 1})

            await self.m.issue_req.call(sim, addr=new_base_addr, data=0, byte_mask=0, store=0)

            await self.wait_until(sim, lambda: len(self.writeback_start_calls) == 1)
            assert list(self.writeback_start_calls) == [old_base_addr]
            assert not self.refill_start_calls

            written_back_words = await self.collect_writeback_line(sim, words_in_line=self.cp.words_in_line)
            assert written_back_words == old_words

            self.allow_writeback_accept = True
            resp = await self.m.accept_res.call(sim)

            assert resp["error"] == 1
            assert resp["data"] == 0
            assert not self.refill_start_calls

            old_tag, index, _ = self.split_addr(old_base_addr)
            stored_tag = self.read_tag_entry(sim, way=0, index=index)
            assert stored_tag["valid"] == 1
            assert stored_tag["dirty"] == 1
            assert stored_tag["tag"] == old_tag

        with self.run_simulation(self.m) as sim:
            sim.add_testbench(cache_process)

    def test_flush_same_set(self):
        async def cache_process(sim: TestbenchContext):
            first_cache_line_addr = 0x00000100
            first_words = [0xDEADBEEF, 0x11223344, 0x55667788, 0x99AABBCC]
            second_cache_line_addr = 0x00000200
            second_words = [0xDEADBEE9, 0x11223349, 0x55667789, 0x99AABBC9]

            await self.wait_for_flush(sim)
            await self.load_line_directly(sim, first_cache_line_addr, first_words, way=0, dirty=1)
            await self.load_line_directly(sim, second_cache_line_addr, second_words, way=1, dirty=0)

            self.writeback_accept_responses.append({"error": 0})

            await self.m.flush_cache.call(sim)
            await self.wait_until(sim, lambda: len(self.writeback_start_calls) == 1)
            assert list(self.writeback_start_calls) == [first_cache_line_addr]
            assert not self.refill_start_calls

            written_back_words = await self.collect_writeback_line(sim, words_in_line=self.cp.words_in_line)
            assert written_back_words == first_words

            self.allow_writeback_accept = True
            await self.wait_for_flush(sim)

            _, first_index, _ = self.split_addr(first_cache_line_addr)
            _, second_index, _ = self.split_addr(second_cache_line_addr)

            first_tag = self.read_tag_entry(sim, way=0, index=first_index)
            second_tag = self.read_tag_entry(sim, way=1, index=second_index)

            assert first_tag["valid"] == 0
            assert first_tag["dirty"] == 0
            assert second_tag["valid"] == 0
            assert second_tag["dirty"] == 0

        with self.run_simulation(self.m) as sim:
            sim.add_testbench(cache_process)

    def test_flush_writeback_error(self):
        async def cache_process(sim: TestbenchContext):
            base_addr = 0x00000100
            words = [0xDEADBEEF, 0x11223344, 0x55667788, 0x99AABBCC]

            await self.wait_for_flush(sim)
            await self.load_line_directly(sim, base_addr, words, way=0, dirty=1)
            self.writeback_accept_responses.append({"error": 1})

            await self.m.flush_cache.call(sim)
            await self.wait_until(sim, lambda: len(self.writeback_start_calls) == 1)
            assert list(self.writeback_start_calls) == [base_addr]

            written_back_words = await self.collect_writeback_line(sim, words_in_line=self.cp.words_in_line)
            assert written_back_words == words

            self.allow_writeback_accept = True
            await self.wait_for_flush(sim)

            tag, index, _ = self.split_addr(base_addr)
            stored_tag = self.read_tag_entry(sim, way=0, index=index)

            assert stored_tag["valid"] == 1
            assert stored_tag["dirty"] == 1
            assert stored_tag["tag"] == tag
            assert not self.refill_start_calls

            hit_resp = await self.call_cache(sim, addr=base_addr)
            assert hit_resp["error"] == 0
            assert hit_resp["data"] == words[0]

        with self.run_simulation(self.m) as sim:
            sim.add_testbench(cache_process)

    def test_miss_prefers_invalid_way(self):
        async def cache_process(sim: TestbenchContext):
            way0_addr = 0x00000100
            refill_addr = self.same_set_addr(way0_addr, 1)
            way0_words = [0x01020304, 0x11121314, 0x21222324, 0x31323334]
            refill_words = [0xAABBCCDD, 0x10203040, 0x50607080, 0x90A0B0C0]

            await self.wait_for_flush(sim)
            await self.load_line_directly(sim, way0_addr, way0_words, way=0, dirty=0)
            self.queue_refill_line(refill_addr, refill_words)

            resp = await self.call_cache(sim, addr=refill_addr)

            assert resp["error"] == 0
            assert resp["data"] == refill_words[0]
            assert list(self.refill_start_calls) == [refill_addr]

            way0_tag, index, _ = self.split_addr(way0_addr)
            refill_tag, _, _ = self.split_addr(refill_addr)
            way0_entry = self.read_tag_entry(sim, way=0, index=index)
            way1_entry = self.read_tag_entry(sim, way=1, index=index)

            assert way0_entry["valid"] == 1
            assert way0_entry["tag"] == way0_tag
            assert way1_entry["valid"] == 1
            assert way1_entry["tag"] == refill_tag

        with self.run_simulation(self.m) as sim:
            sim.add_testbench(cache_process)

    def test_miss_uses_round_robin(self):
        async def cache_process(sim: TestbenchContext):
            way0_addr = 0x00000100
            way1_addr = self.same_set_addr(way0_addr, 1)
            refill_addr = self.same_set_addr(way0_addr, 2)
            way0_words = [0x01020304, 0x11121314, 0x21222324, 0x31323334]
            way1_words = [0x41424344, 0x51525354, 0x61626364, 0x71727374]
            refill_words = [0xAABBCCDD, 0x10203040, 0x50607080, 0x90A0B0C0]

            await self.wait_for_flush(sim)
            await self.load_line_directly(sim, way0_addr, way0_words, way=0, dirty=0)
            await self.load_line_directly(sim, way1_addr, way1_words, way=1, dirty=0)
            self.queue_refill_line(refill_addr, refill_words)

            resp = await self.call_cache(sim, addr=refill_addr)

            assert resp["error"] == 0
            assert resp["data"] == refill_words[0]
            assert list(self.refill_start_calls) == [refill_addr]

            refill_tag, index, _ = self.split_addr(refill_addr)
            way1_tag, _, _ = self.split_addr(way1_addr)
            way0_entry = self.read_tag_entry(sim, way=0, index=index)
            way1_entry = self.read_tag_entry(sim, way=1, index=index)

            assert way0_entry["valid"] == 1
            assert way0_entry["tag"] == refill_tag
            assert way1_entry["valid"] == 1
            assert way1_entry["tag"] == way1_tag

        with self.run_simulation(self.m) as sim:
            sim.add_testbench(cache_process)

    def test_round_robin_advances_only_if_used(self):
        async def cache_process(sim: TestbenchContext):
            way0_addr = 0x00000100
            way1_addr = self.same_set_addr(way0_addr, 1)
            first_refill_addr = self.same_set_addr(way0_addr, 2)
            second_refill_addr = self.same_set_addr(way0_addr, 3)
            third_refill_addr = self.same_set_addr(way0_addr, 4)
            way0_words = [0x01020304, 0x11121314, 0x21222324, 0x31323334]
            first_refill_words = [0xA0A0A0A0, 0xA1A1A1A1, 0xA2A2A2A2, 0xA3A3A3A3]
            way1_words = [0xB0B0B0B0, 0xB1B1B1B1, 0xB2B2B2B2, 0xB3B3B3B3]
            second_refill_words = [0xC0C0C0C0, 0xC1C1C1C1, 0xC2C2C2C2, 0xC3C3C3C3]
            third_refill_words = [0xD0D0D0D0, 0xD1D1D1D1, 0xD2D2D2D2, 0xD3D3D3D3]

            await self.wait_for_flush(sim)
            await self.load_line_directly(sim, way0_addr, way0_words, way=0, dirty=0)

            self.queue_refill_line(first_refill_addr, first_refill_words)
            first_resp = await self.call_cache(sim, addr=first_refill_addr)
            assert first_resp["error"] == 0

            _, index, _ = self.split_addr(way0_addr)
            first_refill_tag, _, _ = self.split_addr(first_refill_addr)
            assert self.read_tag_entry(sim, way=1, index=index)["tag"] == first_refill_tag

            await self.load_line_directly(sim, way1_addr, way1_words, way=1, dirty=0)
            self.queue_refill_line(second_refill_addr, second_refill_words)
            second_resp = await self.call_cache(sim, addr=second_refill_addr)
            assert second_resp["error"] == 0

            second_refill_tag, _, _ = self.split_addr(second_refill_addr)
            assert self.read_tag_entry(sim, way=0, index=index)["tag"] == second_refill_tag

            self.queue_refill_line(third_refill_addr, third_refill_words)
            third_resp = await self.call_cache(sim, addr=third_refill_addr)
            assert third_resp["error"] == 0

            third_refill_tag, _, _ = self.split_addr(third_refill_addr)
            assert self.read_tag_entry(sim, way=1, index=index)["tag"] == third_refill_tag

        with self.run_simulation(self.m) as sim:
            sim.add_testbench(cache_process)
