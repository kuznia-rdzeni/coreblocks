import pytest

from transactron.testing import (
    TestCaseWithSimulator,
    SimpleTestCircuit,
    TestbenchContext,
)

from coreblocks.frontend.bpu.micro_btb import MicroBTB
from coreblocks.arch import CfiType
from coreblocks.params import BranchPredictionConfig, MicroBTBConfig, GenParams
from coreblocks.params import configurations


class TestMicroBTB(TestCaseWithSimulator):
    @pytest.fixture(autouse=True)
    def setup(self, fixture_initialize_testing_env):
        # fetch_block_bytes_log=4 gives fetch_width > 1, so cfi_idx has real bits
        self.config = MicroBTBConfig(entries_log=2)
        self.gen_params = GenParams(
            configurations.test.replace(
                fetch_block_bytes_log=4, bpu_config=BranchPredictionConfig(micro_btb=self.config)
            )
        )
        self.num_entries = 2**self.config.entries_log
        self.useful_max = 2**self.config.useful_cnt_width - 1
        self.btb = SimpleTestCircuit(MicroBTB(self.gen_params, self.config))

    async def lookup(self, sim: TestbenchContext, pc: int):
        """Issue a request and read back the prediction it produces next cycle"""
        await self.btb.request.call(sim, pc=pc)
        return await self.btb.predict.call(sim)

    async def train(self, sim: TestbenchContext, pc, cfi_target, taken, cfi_idx=0, cfi_type=CfiType.BRANCH):
        await self.btb.update.call(
            sim, pc=pc, cfi_target=cfi_target, cfi_idx=cfi_idx, cfi_type=cfi_type, taken=taken, mispredict=0
        )

    def test_unknown_block_misses(self):
        async def proc(sim: TestbenchContext):
            res = await self.lookup(sim, 0x1000)
            assert res["hit"] == 0

        with self.run_simulation(self.btb) as sim:
            sim.add_testbench(proc)

    def test_taken_branch_is_learned(self):
        pc = 0x1000
        target = 0x2ABC

        async def proc(sim: TestbenchContext):
            assert (await self.lookup(sim, pc))["hit"] == 0

            await self.train(sim, pc, target, taken=1)

            res = await self.lookup(sim, pc)
            assert res["hit"] == 1
            assert res["cfi_target"] == target

        with self.run_simulation(self.btb) as sim:
            sim.add_testbench(proc)

    def test_prediction_carries_position_and_type(self):
        pc = 0x1000

        async def proc(sim: TestbenchContext):
            await self.train(sim, pc, cfi_target=0x2000, taken=1, cfi_idx=2, cfi_type=CfiType.JAL)

            res = await self.lookup(sim, pc)
            assert res["hit"] == 1
            assert res["cfi_target"] == 0x2000
            assert res["cfi_idx"] == 2
            assert res["cfi_type"] == CfiType.JAL

        with self.run_simulation(self.btb) as sim:
            sim.add_testbench(proc)

    def test_useful_counter_hysteresis(self):
        pc = 0x1000
        target = 0x2ABC

        async def proc(sim: TestbenchContext):
            await self.train(sim, pc, target, taken=1)
            assert (await self.lookup(sim, pc))["hit"] == 1

            # The usefulness counter starts saturated, so a single not-taken
            # resolution weakens the entry but keeps it valid
            for _ in range(self.useful_max - 1):
                await self.train(sim, pc, cfi_target=0, taken=0)
                assert (await self.lookup(sim, pc))["hit"] == 1

            # One more not-taken drives the counter to zero and invalidates it
            await self.train(sim, pc, cfi_target=0, taken=0)
            assert (await self.lookup(sim, pc))["hit"] == 0

        with self.run_simulation(self.btb) as sim:
            sim.add_testbench(proc)

    def test_not_useful_entry_is_reused(self):
        blocks = [(0x1000 * (i + 1), 0x20000 + 0x1000 * i) for i in range(self.num_entries)]

        async def proc(sim: TestbenchContext):
            for pc, target in blocks:
                await self.train(sim, pc, target, taken=1)

            # Decay the first block until its counter reaches zero (not useful)
            for _ in range(self.useful_max):
                await self.train(sim, blocks[0][0], cfi_target=0, taken=0)

            # A new block must reuse the decayed slot, leaving the others intact
            new_pc, new_target = 0x90000, 0x99000
            await self.train(sim, new_pc, new_target, taken=1)

            assert (await self.lookup(sim, blocks[0][0]))["hit"] == 0

            res = await self.lookup(sim, new_pc)
            assert res["hit"] == 1
            assert res["cfi_target"] == new_target

            for pc, target in blocks[1:]:
                res = await self.lookup(sim, pc)
                assert res["hit"] == 1
                assert res["cfi_target"] == target

        with self.run_simulation(self.btb) as sim:
            sim.add_testbench(proc)

    def test_full_table_evicts_one_entry(self):
        # One more block than there are entries, so the last one must evict
        blocks = [(0x1000 * (i + 1), 0x20000 + 0x1000 * i) for i in range(self.num_entries + 1)]

        async def proc(sim: TestbenchContext):
            for pc, target in blocks:
                await self.train(sim, pc, target, taken=1)

            results = {pc: await self.lookup(sim, pc) for pc, _ in blocks}

            # The table holds num_entries blocks, so exactly one of the num_entries+1
            # must have been evicted - which one is up to the replacement policy
            resident = [pc for pc, res in results.items() if res["hit"]]
            assert len(resident) == self.num_entries

            # The just-installed block survives; the evicted one is an older block
            assert results[blocks[-1][0]]["hit"] == 1

            # Every resident block still predicts its own target
            targets = dict(blocks)
            for pc in resident:
                assert results[pc]["cfi_target"] == targets[pc]

        with self.run_simulation(self.btb) as sim:
            sim.add_testbench(proc)
