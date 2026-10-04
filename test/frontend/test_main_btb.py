import pytest

from transactron.testing import (
    TestCaseWithSimulator,
    SimpleTestCircuit,
    TestbenchContext,
)

from coreblocks.frontend.bpu.main_btb import MainBTB
from coreblocks.arch import CfiType
from coreblocks.params import BimodalConfig, BranchPredictionConfig, MainBTBConfig, GenParams
from coreblocks.params import configurations


class TestMainBTB(TestCaseWithSimulator):
    @pytest.fixture(
        autouse=True,
        params=[
            MainBTBConfig(sets_log=2, ways=4, tag_width=8, target_width=8),
            MainBTBConfig(sets_log=1, ways=2, tag_width=4, target_width=12),
            MainBTBConfig(sets_log=3, ways=8, tag_width=12, target_width=8),
        ],
        ids=["4x4", "2x2", "8x8"],
    )
    def setup(self, fixture_initialize_testing_env, request):
        # Several instructions per block, and targets narrow enough to reach past.
        self.config = request.param
        self.gen_params = GenParams(
            configurations.test.replace(
                fetch_block_bytes_log=4,
                # Unused, but a CFI predictor can't be configured without one.
                bpu_config=BranchPredictionConfig(cfi_predictor=self.config, direction_predictor=BimodalConfig()),
            )
        )
        self.sets = 2**self.config.sets_log
        self.ways = self.config.ways
        self.block_bytes = self.gen_params.fetch_block_bytes
        self.positions = self.gen_params.fetch_width
        self.instr_bytes = self.gen_params.min_instr_width_bytes
        # Max CFIs of one block that fit in a set
        self.block_cfis = min(self.ways, self.positions)
        # How far a stored target can reach
        self.target_region = self.instr_bytes << self.config.target_width

        self.btb = SimpleTestCircuit(MainBTB(self.gen_params, self.config))

    def pc(self, block: int, idx: int = 0) -> int:
        return block * self.block_bytes + idx * self.instr_bytes

    def block_of_set(self, set_idx: int, n: int) -> int:
        return n * self.sets + set_idx

    async def lookup_candidates(self, sim: TestbenchContext, pc: int):
        await self.btb.request_s0.call(sim, pc=pc)
        hints = await self.btb.response_s1.call(sim)
        prediction = await self.btb.response_s2.call(sim)
        return hints, prediction

    async def lookup(self, sim: TestbenchContext, pc: int):
        """Just the earliest candidate."""
        _, prediction = await self.lookup_candidates(sim, pc)
        valid = [candidate for candidate in prediction["candidates"] if candidate["valid"]]
        if not valid:
            return {"hit": 0, "meta": prediction["meta"]}

        candidate = min(valid, key=lambda candidate: candidate["cfi_idx"])
        return {
            "hit": 1,
            "cfi_target": candidate["target"],
            "cfi_idx": candidate["cfi_idx"],
            "cfi_type": candidate["cfi_type"],
            "meta": prediction["meta"],
        }

    async def train(
        self,
        sim: TestbenchContext,
        pc: int,
        cfi_target: int,
        taken: int = 1,
        cfi_idx: int = 0,
        cfi_type=CfiType.BRANCH,
        mispredict: int = 1,
    ):
        meta = (await self.lookup(sim, pc))["meta"]
        await self.train_with_meta(
            sim, pc, meta, cfi_target, taken=taken, cfi_idx=cfi_idx, cfi_type=cfi_type, mispredict=mispredict
        )

    async def train_with_meta(
        self,
        sim: TestbenchContext,
        pc: int,
        meta: int,
        cfi_target: int,
        taken: int = 1,
        cfi_idx: int = 0,
        cfi_type=CfiType.BRANCH,
        mispredict: int = 1,
    ):
        await self.btb.update.call(
            sim,
            pc=pc,
            cfi_target=cfi_target,
            cfi_idx=cfi_idx,
            cfi_type=cfi_type,
            taken=taken,
            mispredict=mispredict,
            meta=meta,
        )

    def ways_of(self, meta: int) -> list[dict]:
        position_width = self.gen_params.fetch_width_log
        type_width = CfiType.as_shape().width
        width = 2 + position_width + type_width
        return [
            {
                "valid": (meta >> (way * width)) & 1,
                "raw_hit": (meta >> (way * width + 1)) & 1,
                "position": (meta >> (way * width + 2)) & ((1 << position_width) - 1),
                "cfi_type": (meta >> (way * width + 2 + position_width)) & ((1 << type_width) - 1),
            }
            for way in range(self.ways)
        ]

    async def make_duplicate(self, sim: TestbenchContext, block: int, other: int, cfi_idx: int, target: int):
        """Store one CFI in ways 0 and 1 by training with a stale snapshot."""
        stale = (await self.lookup(sim, self.pc(block)))["meta"]  # empty set
        await self.train(sim, self.pc(other), target, cfi_idx=cfi_idx)  # way 0
        await self.train(sim, self.pc(block), target, cfi_idx=cfi_idx)  # way 1
        # The stale snapshot still thinks way 0 is free
        await self.train_with_meta(sim, self.pc(block), stale, target, cfi_idx=cfi_idx)

    def test_unknown_block_misses(self):
        async def proc(sim: TestbenchContext):
            assert (await self.lookup(sim, self.pc(0x10)))["hit"] == 0

        with self.run_simulation(self.btb) as sim:
            sim.add_testbench(proc)

    def test_taken_cfi_is_learned(self):
        pc = self.pc(0x10)
        target = self.pc(0x12, 1)

        async def proc(sim: TestbenchContext):
            assert (await self.lookup(sim, pc))["hit"] == 0

            await self.train(sim, pc, target, cfi_idx=1, cfi_type=CfiType.JAL)

            res = await self.lookup(sim, pc)
            assert res["hit"] == 1
            assert res["cfi_target"] == target
            assert res["cfi_idx"] == 1
            assert res["cfi_type"] == CfiType.JAL

        with self.run_simulation(self.btb) as sim:
            sim.add_testbench(proc)

    def test_not_taken_cfi_is_not_allocated(self):
        pc = self.pc(0x10)

        async def proc(sim: TestbenchContext):
            await self.train(sim, pc, cfi_target=self.pc(0x11), taken=0)
            assert (await self.lookup(sim, pc))["hit"] == 0

        with self.run_simulation(self.btb) as sim:
            sim.add_testbench(proc)

    def test_correct_prediction_is_not_trained(self):
        pc = self.pc(0x10)

        async def proc(sim: TestbenchContext):
            await self.train(sim, pc, cfi_target=self.pc(0x11), mispredict=0)
            assert (await self.lookup(sim, pc))["hit"] == 0

        with self.run_simulation(self.btb) as sim:
            sim.add_testbench(proc)

    def test_not_taken_branch_keeps_its_entry(self):
        # Direction isn't the BTB's business
        pc = self.pc(0x10)
        target = self.pc(0x11)

        async def proc(sim: TestbenchContext):
            await self.train(sim, pc, target)
            await self.train(sim, pc, cfi_target=self.pc(0x14), taken=0)

            res = await self.lookup(sim, pc)
            assert res["hit"] == 1
            assert res["cfi_target"] == target

        with self.run_simulation(self.btb) as sim:
            sim.add_testbench(proc)

    def test_two_cfis_of_one_block(self):
        block = 0x10
        first, second = 1, self.positions - 2
        first_target = self.pc(0x12)
        second_target = self.pc(0x14)

        async def proc(sim: TestbenchContext):
            await self.train(sim, self.pc(block), first_target, cfi_idx=first, cfi_type=CfiType.JAL)
            await self.train(sim, self.pc(block), second_target, cfi_idx=second, cfi_type=CfiType.BRANCH)

            # Entering at the start
            res = await self.lookup(sim, self.pc(block))
            assert res["hit"] == 1
            assert res["cfi_idx"] == first
            assert res["cfi_target"] == first_target
            assert res["cfi_type"] == CfiType.JAL

            # Entering past the first CFI
            res = await self.lookup(sim, self.pc(block, first + 1))
            assert res["hit"] == 1
            assert res["cfi_idx"] == second
            assert res["cfi_target"] == second_target
            assert res["cfi_type"] == CfiType.BRANCH

            # Entering past both
            assert (await self.lookup(sim, self.pc(block, second + 1)))["hit"] == 0

        with self.run_simulation(self.btb) as sim:
            sim.add_testbench(proc)

    def test_s1_hints_and_s2_return_all_cfis(self):
        block = 0x10
        first, second = 1, self.positions - 2

        async def proc(sim: TestbenchContext):
            await self.train(sim, self.pc(block), self.pc(0x12), cfi_idx=first, cfi_type=CfiType.JAL)
            await self.train(sim, self.pc(block), self.pc(0x14), cfi_idx=second, cfi_type=CfiType.BRANCH)

            hints, prediction = await self.lookup_candidates(sim, self.pc(block))
            valid_hints = sorted(
                (hint for hint in hints["candidates"] if hint["valid"]), key=lambda hint: hint["cfi_idx"]
            )
            valid_candidates = sorted(
                (candidate for candidate in prediction["candidates"] if candidate["valid"]),
                key=lambda candidate: candidate["cfi_idx"],
            )

            assert [hint["cfi_idx"] for hint in valid_hints] == [first, second]
            assert [candidate["cfi_idx"] for candidate in valid_candidates] == [first, second]
            assert [candidate["target_valid"] for candidate in valid_candidates] == [1, 1]

        with self.run_simulation(self.btb) as sim:
            sim.add_testbench(proc)

    def test_whole_set_holds_cfis_of_one_block(self):
        block = 0x10
        positions = list(range(self.block_cfis))
        targets = [self.pc(0x20 + i) for i in positions]

        async def proc(sim: TestbenchContext):
            for idx, target in zip(positions, targets):
                await self.train(sim, self.pc(block), target, cfi_idx=idx)

            for idx, target in zip(positions, targets):
                res = await self.lookup(sim, self.pc(block, idx))
                assert res["hit"] == 1
                assert res["cfi_idx"] == idx
                assert res["cfi_target"] == target

        with self.run_simulation(self.btb) as sim:
            sim.add_testbench(proc)

    def test_stale_snapshot_stores_one_cfi_twice(self):
        block, other = self.block_of_set(0, 0), self.block_of_set(0, 1)
        idx, target = 0, self.pc(0x30)

        async def proc(sim: TestbenchContext):
            await self.make_duplicate(sim, block, other, idx, target)

            ways = self.ways_of((await self.lookup(sim, self.pc(block)))["meta"])
            holding = [way for way in ways if way["raw_hit"] and way["position"] == idx]
            assert len(holding) == 2

        with self.run_simulation(self.btb) as sim:
            sim.add_testbench(proc)

    def test_duplicate_cfi_is_predicted_once(self):
        # The BPU must never see two candidates for one instruction.
        block, other = self.block_of_set(0, 0), self.block_of_set(0, 1)
        idx, target = 0, self.pc(0x30)

        async def proc(sim: TestbenchContext):
            await self.make_duplicate(sim, block, other, idx, target)

            hints, prediction = await self.lookup_candidates(sim, self.pc(block))
            assert [hint["cfi_idx"] for hint in hints["candidates"] if hint["valid"]] == [idx]
            candidates = [c for c in prediction["candidates"] if c["valid"]]
            assert len(candidates) == 1
            assert candidates[0]["cfi_idx"] == idx
            assert candidates[0]["target"] == target

        with self.run_simulation(self.btb) as sim:
            sim.add_testbench(proc)

    def test_next_training_purges_the_duplicate(self):
        block, other = self.block_of_set(0, 0), self.block_of_set(0, 1)
        idx, target = 0, self.pc(0x30)

        async def proc(sim: TestbenchContext):
            await self.make_duplicate(sim, block, other, idx, target)

            await self.train(sim, self.pc(block), target, cfi_idx=idx)

            ways = self.ways_of((await self.lookup(sim, self.pc(block)))["meta"])
            holding = [way for way in ways if way["raw_hit"] and way["position"] == idx]
            assert len(holding) == 1

            res = await self.lookup(sim, self.pc(block))
            assert res["hit"] == 1
            assert res["cfi_idx"] == idx
            assert res["cfi_target"] == target

        with self.run_simulation(self.btb) as sim:
            sim.add_testbench(proc)

    def test_purged_way_is_free_again(self):
        block, other = self.block_of_set(0, 0), self.block_of_set(0, 1)
        idx, target = 0, self.pc(0x30)

        async def proc(sim: TestbenchContext):
            await self.make_duplicate(sim, block, other, idx, target)
            before = self.ways_of((await self.lookup(sim, self.pc(block)))["meta"])
            assert sum(way["valid"] for way in before) == 2

            await self.train(sim, self.pc(block), target, cfi_idx=idx)

            after = self.ways_of((await self.lookup(sim, self.pc(block)))["meta"])
            assert sum(way["valid"] for way in after) == 1

        with self.run_simulation(self.btb) as sim:
            sim.add_testbench(proc)

    def test_indirect_target_is_retrained_in_place(self):
        block = 0x10
        first_target = self.pc(0x12)
        second_target = self.pc(0x14)

        async def proc(sim: TestbenchContext):
            await self.train(sim, self.pc(block), first_target, cfi_idx=1, cfi_type=CfiType.JALR)
            await self.train(sim, self.pc(block), second_target, cfi_idx=1, cfi_type=CfiType.JALR)

            res = await self.lookup(sim, self.pc(block))
            assert res["hit"] == 1
            assert res["cfi_target"] == second_target

            # The way was reused, so the rest of the set still fits the other CFIs
            others = [idx for idx in range(self.positions) if idx != 1][: self.block_cfis - 1]
            for idx in others:
                await self.train(sim, self.pc(block), self.pc(0x30 + idx), cfi_idx=idx)

            for idx in others:
                res = await self.lookup(sim, self.pc(block, idx))
                assert res["cfi_idx"] == idx
                assert res["cfi_target"] == self.pc(0x30 + idx)
            res = await self.lookup(sim, self.pc(block, 1))
            assert res["cfi_idx"] == 1
            assert res["cfi_target"] == second_target

        with self.run_simulation(self.btb) as sim:
            sim.add_testbench(proc)

    @pytest.mark.parametrize("cfi_type", [CfiType.JAL, CfiType.BRANCH])
    def test_aliased_direct_target_is_retrained(self, cfi_type):
        pc = self.pc(0x10)
        alias = pc + (1 << (self.gen_params.fetch_block_bytes_log + self.config.sets_log + self.config.tag_width))
        target = alias + 2 * self.block_bytes

        async def proc(sim: TestbenchContext):
            await self.train(sim, pc, pc + self.block_bytes, cfi_type=cfi_type)
            assert (await self.lookup(sim, alias))["cfi_target"] != target

            await self.train(sim, alias, target, cfi_type=cfi_type)

            prediction = await self.lookup(sim, alias)
            assert prediction["cfi_target"] == target
            assert sum(way["valid"] for way in self.ways_of(prediction["meta"])) == 1

        with self.run_simulation(self.btb) as sim:
            sim.add_testbench(proc)

    @pytest.mark.parametrize("cfi_type", [CfiType.JAL, CfiType.BRANCH])
    def test_changed_direct_target_is_retrained(self, cfi_type):
        pc = self.pc(0x10)
        target = pc + 2 * self.block_bytes

        async def proc(sim: TestbenchContext):
            await self.train(sim, pc, pc + self.block_bytes, cfi_type=cfi_type)
            await self.train(sim, pc, target, cfi_type=cfi_type)
            assert (await self.lookup(sim, pc))["cfi_target"] == target

        with self.run_simulation(self.btb) as sim:
            sim.add_testbench(proc)

    def test_changed_cfi_type_is_retrained_in_place(self):
        block = 0x10
        target = self.pc(0x12)

        async def proc(sim: TestbenchContext):
            await self.train(sim, self.pc(block), target, cfi_idx=1, cfi_type=CfiType.BRANCH)
            await self.train(sim, self.pc(block), target, cfi_idx=1, cfi_type=CfiType.JALR)

            res = await self.lookup(sim, self.pc(block))
            assert res["hit"] == 1
            assert res["cfi_type"] == CfiType.JALR

        with self.run_simulation(self.btb) as sim:
            sim.add_testbench(proc)

    def test_blocks_of_one_set_conflict(self):
        blocks = [self.block_of_set(1, n) for n in range(self.ways + 1)]
        targets = {block: self.pc(0x40 + n) for n, block in enumerate(blocks)}

        async def proc(sim: TestbenchContext):
            for block in blocks:
                await self.train(sim, self.pc(block), targets[block])

            results = {block: await self.lookup(sim, self.pc(block)) for block in blocks}

            # One got evicted, which one is up to the replacement policy
            resident = [block for block, res in results.items() if res["hit"]]
            assert len(resident) == self.ways
            assert results[blocks[-1]]["hit"] == 1

            for block in resident:
                assert results[block]["cfi_target"] == targets[block]

        with self.run_simulation(self.btb) as sim:
            sim.add_testbench(proc)

    def test_repeated_conflicts_replace_every_way(self):
        # Every way should eventually get replaced.
        async def proc(sim: TestbenchContext):
            residents = {}
            for n in range(self.ways):
                block = self.block_of_set(1, n)
                await self.train(sim, self.pc(block), self.pc(0x40))
                _, prediction = await self.lookup_candidates(sim, self.pc(block))
                way = next(i for i, candidate in enumerate(prediction["candidates"]) if candidate["valid"])
                residents[way] = block

            block = self.block_of_set(1, self.ways)
            replaced = set()
            for _ in range(32):
                assert not (await self.lookup(sim, self.pc(block)))["hit"]
                await self.train(sim, self.pc(block), self.pc(0x40))
                _, prediction = await self.lookup_candidates(sim, self.pc(block))
                valid = [i for i, candidate in enumerate(prediction["candidates"]) if candidate["valid"]]
                assert len(valid) == 1
                way = valid[0]
                replaced.add(way)
                residents[way], block = block, residents[way]
                assert not (await self.lookup(sim, self.pc(block)))["hit"]

            assert replaced == set(range(self.ways))

        with self.run_simulation(self.btb) as sim:
            sim.add_testbench(proc)

    def test_blocks_of_different_sets_do_not_conflict(self):
        blocks = [self.block_of_set(s, 0) for s in range(self.sets)]
        targets = {block: self.pc(0x40 + n) for n, block in enumerate(blocks)}

        async def proc(sim: TestbenchContext):
            for block in blocks:
                await self.train(sim, self.pc(block), targets[block])

            for block in blocks:
                res = await self.lookup(sim, self.pc(block))
                assert res["hit"] == 1
                assert res["cfi_target"] == targets[block]

        with self.run_simulation(self.btb) as sim:
            sim.add_testbench(proc)

    def test_target_carry(self):
        # Separate blocks, so that even the 2-way config holds all three
        def block_pc(n: int) -> int:
            return self.pc(0x10 + n) + self.target_region

        offsets = [self.block_bytes, self.target_region, -self.target_region]

        async def proc(sim: TestbenchContext):
            for n, offset in enumerate(offsets):
                await self.train(sim, block_pc(n), block_pc(n) + offset, cfi_idx=1, cfi_type=CfiType.JAL)

            for n, offset in enumerate(offsets):
                res = await self.lookup(sim, block_pc(n))
                assert res["hit"] == 1
                assert res["cfi_target"] == block_pc(n) + offset

        with self.run_simulation(self.btb) as sim:
            sim.add_testbench(proc)

    def test_target_out_of_reach_is_mispredicted(self):
        pc = self.pc(0x10) + self.target_region
        target = pc + 3 * self.target_region

        async def proc(sim: TestbenchContext):
            await self.train(sim, pc, target, cfi_idx=1, cfi_type=CfiType.JAL)
            res = await self.lookup(sim, pc)
            assert res["hit"] == 1
            assert res["cfi_target"] != target

        with self.run_simulation(self.btb) as sim:
            sim.add_testbench(proc)
