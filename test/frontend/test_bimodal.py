import pytest

from transactron.testing import SimpleTestCircuit, TestbenchContext, TestCaseWithSimulator

from coreblocks.arch import CfiType
from coreblocks.frontend.bpu.bimodal import Bimodal
from coreblocks.params import BimodalConfig, BranchPredictionConfig, GenParams, MainBTBConfig
from coreblocks.params import configurations


class TestBimodal(TestCaseWithSimulator):
    @pytest.fixture(autouse=True)
    def setup(self, fixture_initialize_testing_env):
        self.config = BimodalConfig(sets_log=2, counter_width=2)
        cfi_config = MainBTBConfig(sets_log=2, ways=2, tag_width=8, target_width=8)
        self.gen_params = GenParams(
            configurations.test.replace(
                fetch_block_bytes_log=4,
                bpu_config=BranchPredictionConfig(
                    cfi_predictor=cfi_config,
                    direction_predictor=self.config,
                ),
            )
        )
        self.bimodal = SimpleTestCircuit(Bimodal(self.gen_params, self.config))
        self.empty_hints = {"candidates": [{"valid": 0, "cfi_idx": 0, "cfi_type": CfiType.INVALID}] * 2}

    async def lookup(self, sim: TestbenchContext, pc: int):
        await self.bimodal.request_s0.call(sim, pc=pc)
        await self.bimodal.accept_s1_hints.call(sim, pc=pc, hints=self.empty_hints)
        return await self.bimodal.response_s2.call(sim)

    async def train(
        self,
        sim: TestbenchContext,
        pc: int,
        meta: int,
        branch_mask: int,
        cfi_idx: int,
        taken: int,
    ):
        await self.bimodal.update.call(
            sim,
            pc=pc,
            branch_mask=branch_mask,
            cfi_target=0,
            cfi_idx=cfi_idx,
            cfi_type=CfiType.BRANCH,
            taken=taken,
            mispredict=0,
            meta=meta,
        )

    def counter(self, meta: int, position: int) -> int:
        mask = (1 << self.config.counter_width) - 1
        return (meta >> (position * self.config.counter_width)) & mask

    def test_counters_start_weakly_not_taken(self):
        async def proc(sim: TestbenchContext):
            prediction = await self.lookup(sim, 0x1000)
            assert prediction["taken"] == 0
            for position in range(self.gen_params.fetch_width):
                assert self.counter(prediction["meta"], position) == 1

        with self.run_simulation(self.bimodal) as sim:
            sim.add_testbench(proc)

    def test_taken_and_not_taken_updates_saturate(self):
        pc = 0x1000
        position = 1

        async def proc(sim: TestbenchContext):
            for _ in range(4):
                prediction = await self.lookup(sim, pc)
                await self.train(sim, pc, prediction["meta"], 1 << position, position, taken=1)

            prediction = await self.lookup(sim, pc)
            assert self.counter(prediction["meta"], position) == 3
            assert prediction["taken"] & (1 << position)

            for _ in range(5):
                prediction = await self.lookup(sim, pc)
                await self.train(sim, pc, prediction["meta"], 1 << position, position, taken=0)

            prediction = await self.lookup(sim, pc)
            assert self.counter(prediction["meta"], position) == 0
            assert not prediction["taken"] & (1 << position)

        with self.run_simulation(self.bimodal) as sim:
            sim.add_testbench(proc)

    def test_branch_mask_trains_every_executed_branch(self):
        pc = 0x1000
        first, second = 1, 2

        async def proc(sim: TestbenchContext):
            for position in (first, second):
                prediction = await self.lookup(sim, pc)
                await self.train(sim, pc, prediction["meta"], 1 << position, position, taken=1)

            prediction = await self.lookup(sim, pc)
            assert prediction["taken"] & (1 << first)
            assert prediction["taken"] & (1 << second)

            await self.train(
                sim,
                pc,
                prediction["meta"],
                (1 << first) | (1 << second),
                second,
                taken=1,
            )
            prediction = await self.lookup(sim, pc)
            assert not prediction["taken"] & (1 << first)
            assert prediction["taken"] & (1 << second)

        with self.run_simulation(self.bimodal) as sim:
            sim.add_testbench(proc)

    def test_back_to_back_same_row_updates_are_forwarded(self):
        pc = 0x1000
        position = 1

        async def proc(sim: TestbenchContext):
            old = await self.lookup(sim, pc)
            await self.train(sim, pc, old["meta"], 1 << position, position, taken=1)
            await self.train(sim, pc, old["meta"], 1 << position, position, taken=1)

            prediction = await self.lookup(sim, pc)
            assert self.counter(prediction["meta"], position) == 3

        with self.run_simulation(self.bimodal) as sim:
            sim.add_testbench(proc)

    def test_alternating_positions_preserve_forwarded_counters(self):
        pc = 0x1000
        first, second = 1, 2

        async def proc(sim: TestbenchContext):
            old = await self.lookup(sim, pc)
            for position in (first, second, first, second):
                await self.train(sim, pc, old["meta"], 1 << position, position, taken=1)

            prediction = await self.lookup(sim, pc)
            assert self.counter(prediction["meta"], first) == 3
            assert self.counter(prediction["meta"], second) == 3

        with self.run_simulation(self.bimodal) as sim:
            sim.add_testbench(proc)

    def test_switching_rows_resets_forwarded_positions(self):
        pc = 0x1000
        other_pc = pc + self.gen_params.fetch_block_bytes
        first, second = 1, 2

        async def proc(sim: TestbenchContext):
            old = await self.lookup(sim, pc)
            other = await self.lookup(sim, other_pc)
            await self.train(sim, pc, old["meta"], 1 << first, first, taken=1)
            await self.train(sim, other_pc, other["meta"], 1 << second, second, taken=1)
            await self.train(sim, other_pc, other["meta"], 1 << first, first, taken=1)

            prediction = await self.lookup(sim, other_pc)
            assert self.counter(prediction["meta"], first) == 2
            assert self.counter(prediction["meta"], second) == 2

        with self.run_simulation(self.bimodal) as sim:
            sim.add_testbench(proc)

    def test_stale_metadata_does_not_overwrite_untouched_counter(self):
        pc = 0x1000
        other_pc = pc + self.gen_params.fetch_block_bytes
        first, second = 1, 2

        async def proc(sim: TestbenchContext):
            first_snapshot = await self.lookup(sim, pc)
            stale_snapshot = await self.lookup(sim, pc)
            other_snapshot = await self.lookup(sim, other_pc)

            await self.train(sim, pc, first_snapshot["meta"], 1 << first, first, taken=1)
            await self.train(sim, other_pc, other_snapshot["meta"], 1, 0, taken=1)
            await self.train(sim, pc, stale_snapshot["meta"], 1 << second, second, taken=1)

            prediction = await self.lookup(sim, pc)
            assert prediction["taken"] & (1 << first)
            assert prediction["taken"] & (1 << second)

        with self.run_simulation(self.bimodal) as sim:
            sim.add_testbench(proc)

    def test_different_rows_are_independent(self):
        first_pc = 0x1000
        second_pc = first_pc + self.gen_params.fetch_block_bytes

        async def proc(sim: TestbenchContext):
            first = await self.lookup(sim, first_pc)
            await self.train(sim, first_pc, first["meta"], 1, 0, taken=1)

            assert (await self.lookup(sim, first_pc))["taken"] & 1
            assert not (await self.lookup(sim, second_pc))["taken"] & 1

        with self.run_simulation(self.bimodal) as sim:
            sim.add_testbench(proc)
