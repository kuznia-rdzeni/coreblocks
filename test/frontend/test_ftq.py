import pytest
from collections import deque
from dataclasses import dataclass

from transactron.testing import (
    TestCaseWithSimulator,
    def_method_mock,
    SimpleTestCircuit,
    TestbenchContext,
    ProcessContext,
)
from transactron.testing.method_mock import MethodMock

from transactron.utils import DependencyContext, ModuleConnector

from coreblocks.arch import CfiType
from coreblocks.frontend.ftq import FetchTargetQueue
from coreblocks.interface.keys import CSRInstancesKey
from coreblocks.params import BranchPredictionConfig, GenParams, MicroBTBConfig
from coreblocks.params import configurations
from coreblocks.priv.csr.csr_instances import CSRInstances


@dataclass(frozen=True)
class DummyMicroBTBConfig(MicroBTBConfig):
    META_WIDTH = 8

    def meta_width(self, fetch_width: int) -> int:
        return self.META_WIDTH


class TestFetchTargetQueue(TestCaseWithSimulator):
    @pytest.fixture(autouse=True)
    def setup(self, fixture_initialize_testing_env):
        self.start_pc = 0x100
        self.gen_params = GenParams(configurations.test.replace(start_pc=self.start_pc))
        self.ifu_requests: deque = deque()
        self.bpu_requests: deque = deque()
        self.bpu_updates: deque = deque()
        self.bpu_flush_count: int = 0

        self.csr_instances = CSRInstances(self.gen_params)
        DependencyContext.get().add_dependency(CSRInstancesKey(), self.csr_instances)

        self.ftq = SimpleTestCircuit(FetchTargetQueue(self.gen_params))
        self.dut = ModuleConnector(ftq=self.ftq, csr_instances=self.csr_instances)

    @def_method_mock(lambda self: self.ftq.stall_guard)
    def stall_guard_mock(self):
        pass

    @def_method_mock(lambda self: self.ftq.bpu_flush)
    def bpu_flush_mock(self):
        @MethodMock.effect
        def eff():
            self.bpu_flush_count += 1

    @def_method_mock(lambda self: self.ftq.bpu_update)
    def bpu_update_mock(self, pc, branch_mask, cfi_valid, cfi_target, cfi_idx, cfi_type, taken, mispredict, meta):
        @MethodMock.effect
        def eff():
            self.bpu_updates.append(
                {
                    "pc": pc,
                    "cfi_target": cfi_target,
                    "cfi_idx": cfi_idx,
                    "cfi_type": cfi_type,
                    "taken": taken,
                    "mispredict": mispredict,
                }
            )

    @def_method_mock(lambda self: self.ftq.bpu_request)
    def bpu_request_mock(self, pc, ftq_ptr):
        @MethodMock.effect
        def eff():
            self.bpu_requests.append(pc)

    @def_method_mock(lambda self: self.ftq.ifu_request)
    def ifu_request_mock(self, pc, ftq_ptr, fetch_gen):
        @MethodMock.effect
        def eff():
            self.ifu_requests.append(
                {"pc": pc, "ftq_ptr": ftq_ptr["ptr"], "parity": ftq_ptr["parity"], "fetch_gen": fetch_gen}
            )

    async def check_stale(self, sim: TestbenchContext, req: dict) -> int:
        res = await self.ftq.check_stale[0].call(
            sim, ftq_ptr={"ptr": req["ftq_ptr"], "parity": req["parity"]}, fetch_gen=req["fetch_gen"]
        )
        return res["stale"]

    async def auto_bpu_process(self, sim: ProcessContext):
        """Responds to each BPU request by predicting PC+4 as the next PC."""
        while True:
            if self.bpu_requests:
                pc = self.bpu_requests.popleft()
                await self.ftq.bpu_fetch_target.call(sim, pc=pc + 4, ftq_ptr={"ptr": 0, "parity": 0})
            else:
                await sim.tick()

    def test_alloc_sends_ifu_request_with_start_pc(self):
        async def proc(sim: TestbenchContext):
            for _ in range(5):
                await sim.tick()
            assert len(self.ifu_requests) >= 1
            assert self.ifu_requests[0]["pc"] == self.start_pc
            assert self.ifu_requests[0]["ftq_ptr"] == 0

        with self.run_simulation(self.dut) as sim:
            sim.add_process(self.auto_bpu_process)
            sim.add_testbench(proc)

    def test_sequential_allocs_advance_ftq_ptr(self):
        n_allocs = 4

        async def proc(sim: TestbenchContext):
            for _ in range(20):
                await sim.tick()
            assert len(self.ifu_requests) >= n_allocs
            for i in range(n_allocs):
                assert self.ifu_requests[i]["pc"] == self.start_pc + 4 * i
                assert self.ifu_requests[i]["ftq_ptr"] == i

        with self.run_simulation(self.dut) as sim:
            sim.add_process(self.auto_bpu_process)
            sim.add_testbench(proc)

    def test_ifu_writeback_triggers_bpu_flush(self):
        async def proc(sim: TestbenchContext):
            for _ in range(5):
                await sim.tick()
            flush_count_before = self.bpu_flush_count
            await self.ftq.ifu_writeback.call(
                sim, ftq_ptr={"ptr": 0, "parity": 0}, redirect=0, stall=1, cfi_idx=0, cfi_type=0, cfi_target=0
            )
            assert self.bpu_flush_count > flush_count_before

        with self.run_simulation(self.dut) as sim:
            sim.add_process(self.auto_bpu_process)
            sim.add_testbench(proc)

    def test_ifu_writeback_restarts_fetch_from_new_pc(self):
        # ifu_writeback calls FAU.ifu_redirect which sets the new PC directly,
        # so the next alloc uses redirect_pc without needing a BPU response.
        redirect_pc = 0x200

        async def proc(sim: TestbenchContext):
            await self.ftq.ifu_writeback.call(
                sim,
                ftq_ptr={"ptr": 0, "parity": 0},
                redirect=1,
                stall=0,
                cfi_idx=0,
                cfi_type=0,
                cfi_target=redirect_pc,
            )
            for _ in range(5):
                await sim.tick()
            assert redirect_pc in [req["pc"] for req in self.ifu_requests]

        with self.run_simulation(self.dut) as sim:
            sim.add_testbench(proc)

    def test_backend_redirect_restarts_fetch_from_new_pc(self):
        # backend_redirect calls FAU.backend_redirect which sets the new PC directly.
        redirect_pc = 0x400

        async def proc(sim: TestbenchContext):
            await self.ftq.backend_redirect.call(sim, pc=redirect_pc)
            for _ in range(5):
                await sim.tick()
            assert redirect_pc in [req["pc"] for req in self.ifu_requests]

        with self.run_simulation(self.dut) as sim:
            sim.add_testbench(proc)

    def test_backend_redirect_triggers_bpu_flush(self):
        async def proc(sim: TestbenchContext):
            flush_count_before = self.bpu_flush_count
            await self.ftq.backend_redirect.call(sim, ftq_ptr={"ptr": 0, "parity": 0}, pc=0x400)
            assert self.bpu_flush_count == flush_count_before + 1

        with self.run_simulation(self.dut) as sim:
            sim.add_testbench(proc)

    def test_fetch_gen_starts_at_one_and_is_unique_per_entry(self):
        # Each entry is issued exactly once as fetch advances, so every request carries
        # generation 1
        n_allocs = 4

        async def proc(sim: TestbenchContext):
            for _ in range(20):
                await sim.tick()
            assert len(self.ifu_requests) >= n_allocs
            for i in range(n_allocs):
                assert self.ifu_requests[i]["ftq_ptr"] == i
                assert self.ifu_requests[i]["fetch_gen"] == 1

        with self.run_simulation(self.dut) as sim:
            sim.add_process(self.auto_bpu_process)
            sim.add_testbench(proc)

    def test_check_stale_false_for_inflight_request(self):
        async def proc(sim: TestbenchContext):
            for _ in range(10):
                await sim.tick()
            assert len(self.ifu_requests) >= 3
            assert await self.check_stale(sim, self.ifu_requests[0]) == 0

        with self.run_simulation(self.dut) as sim:
            sim.add_process(self.auto_bpu_process)
            sim.add_testbench(proc)

    def test_check_stale_true_on_generation_mismatch(self):
        # Querying a real entry with a generation it was never issued with is stale
        async def proc(sim: TestbenchContext):
            for _ in range(10):
                await sim.tick()
            assert len(self.ifu_requests) >= 3
            req = dict(self.ifu_requests[0])
            req["fetch_gen"] = 0
            assert await self.check_stale(sim, req) == 1

        with self.run_simulation(self.dut) as sim:
            sim.add_process(self.auto_bpu_process)
            sim.add_testbench(proc)

    def test_check_stale_true_for_not_yet_fetched_entry(self):
        async def proc(sim: TestbenchContext):
            for _ in range(10):
                await sim.tick()
            future = {"ftq_ptr": self.gen_params.ftq_size - 1, "parity": 0, "fetch_gen": 1}
            assert await self.check_stale(sim, future) == 1

        with self.run_simulation(self.dut) as sim:
            sim.add_process(self.auto_bpu_process)
            sim.add_testbench(proc)

    def test_ifu_redirect_makes_squashed_requests_stale(self):
        redirect_pc = 0x500

        async def proc(sim: TestbenchContext):
            for _ in range(15):
                await sim.tick()
            assert len(self.ifu_requests) >= 4
            before = self.ifu_requests[0]
            squashed = self.ifu_requests[3]
            assert before["ftq_ptr"] == 0
            assert squashed["ftq_ptr"] == 3

            # Both requests are valid before the redirect.
            assert await self.check_stale(sim, before) == 0
            assert await self.check_stale(sim, squashed) == 0

            n_before_redirect = len(self.ifu_requests)

            await self.ftq.ifu_writeback.call(
                sim,
                ftq_ptr={"ptr": 1, "parity": 0},
                redirect=1,
                stall=0,
                cfi_idx=0,
                cfi_type=0,
                cfi_target=redirect_pc,
            )

            # The squashed request is now stale; the one before the redirect point is untouched.
            assert await self.check_stale(sim, squashed) == 1
            assert await self.check_stale(sim, before) == 0

            # Fetch resumes from the redirect target and re-issues the squashed entry with a
            # bumped generation. The old (stale) request stays stale
            for _ in range(15):
                await sim.tick()
            new_requests = list(self.ifu_requests)[n_before_redirect:]
            reissued = [req for req in new_requests if req["ftq_ptr"] == squashed["ftq_ptr"]]
            assert reissued, "the squashed entry should have been re-fetched"
            assert reissued[0]["fetch_gen"] != squashed["fetch_gen"]
            assert await self.check_stale(sim, reissued[0]) == 0
            assert await self.check_stale(sim, squashed) == 1

        with self.run_simulation(self.dut) as sim:
            sim.add_process(self.auto_bpu_process)
            sim.add_testbench(proc)


class TestFetchTargetQueueFull(TestCaseWithSimulator):
    @pytest.fixture(autouse=True)
    def setup(self, fixture_initialize_testing_env):
        self.start_pc = 0x100
        # small FTQ (4 entries) to exercise the full condition quickly
        self.gen_params = GenParams(configurations.test.replace(start_pc=self.start_pc, ftq_size_log=2))
        self.ifu_requests: deque = deque()
        self.bpu_requests: deque = deque()

        self.csr_instances = CSRInstances(self.gen_params)
        DependencyContext.get().add_dependency(CSRInstancesKey(), self.csr_instances)

        self.ftq = SimpleTestCircuit(FetchTargetQueue(self.gen_params))
        self.dut = ModuleConnector(ftq=self.ftq, csr_instances=self.csr_instances)

    @def_method_mock(lambda self: self.ftq.stall_guard)
    def stall_guard_mock(self):
        pass

    @def_method_mock(lambda self: self.ftq.bpu_flush)
    def bpu_flush_mock(self):
        pass

    @def_method_mock(lambda self: self.ftq.bpu_update)
    def bpu_update_mock(self, pc, branch_mask, cfi_valid, cfi_target, cfi_idx, cfi_type, taken, mispredict, meta):
        pass

    @def_method_mock(lambda self: self.ftq.bpu_request)
    def bpu_request_mock(self, pc, ftq_ptr):
        @MethodMock.effect
        def eff():
            self.bpu_requests.append(pc)

    @def_method_mock(lambda self: self.ftq.ifu_request)
    def ifu_request_mock(self, pc, ftq_ptr, fetch_gen):
        @MethodMock.effect
        def eff():
            self.ifu_requests.append(pc)

    async def auto_bpu_process(self, sim: ProcessContext):
        while True:
            if self.bpu_requests:
                pc = self.bpu_requests.popleft()
                await self.ftq.bpu_fetch_target.call(sim, pc=pc + 4, ftq_ptr={"ptr": 0, "parity": 0})
            else:
                await sim.tick()

    def test_ftq_full_stalls_then_commit_unblocks(self):
        ftq_size = self.gen_params.ftq_size  # 4

        async def proc(sim: TestbenchContext):
            # Let the FTQ fill up
            for _ in range(20):
                await sim.tick()
            count_when_full = len(self.ifu_requests)
            assert count_when_full == ftq_size

            # Wait a few more cycles to confirm no new requests come in
            for _ in range(5):
                await sim.tick()
            assert len(self.ifu_requests) == count_when_full

            # Commit entry 1, freeing one slot
            await self.ftq.commit.call(sim, ftq_ptr={"ptr": 1, "parity": 0})

            # Wait for one more alloc
            for _ in range(5):
                await sim.tick()
            assert len(self.ifu_requests) == ftq_size + 1

        with self.run_simulation(self.dut) as sim:
            sim.add_process(self.auto_bpu_process)
            sim.add_testbench(proc)


class TestFetchTargetQueueTrain(TestCaseWithSimulator):
    @pytest.fixture(autouse=True)
    def setup(self, fixture_initialize_testing_env):
        self.start_pc = 0x100
        # 4-instruction fetch blocks so CFI indices distinguish resolves within a block
        self.gen_params = GenParams(
            configurations.test.replace(
                start_pc=self.start_pc,
                fetch_block_bytes_log=4,
                bpu_config=BranchPredictionConfig(fast_predictor=DummyMicroBTBConfig()),
            )
        )
        self.meta = 0xA5
        self.bpu_requests: deque = deque()
        self.bpu_updates: deque = deque()

        self.csr_instances = CSRInstances(self.gen_params)
        DependencyContext.get().add_dependency(CSRInstancesKey(), self.csr_instances)

        self.ftq = SimpleTestCircuit(FetchTargetQueue(self.gen_params))
        self.dut = ModuleConnector(ftq=self.ftq, csr_instances=self.csr_instances)

    @def_method_mock(lambda self: self.ftq.stall_guard)
    def stall_guard_mock(self):
        pass

    @def_method_mock(lambda self: self.ftq.bpu_flush)
    def bpu_flush_mock(self):
        pass

    @def_method_mock(lambda self: self.ftq.bpu_request)
    def bpu_request_mock(self, pc, ftq_ptr):
        @MethodMock.effect
        def eff():
            self.bpu_requests.append(pc)

    @def_method_mock(lambda self: self.ftq.ifu_request)
    def ifu_request_mock(self, pc, ftq_ptr, fetch_gen):
        pass

    @def_method_mock(lambda self: self.ftq.bpu_update)
    def bpu_update_mock(self, pc, branch_mask, cfi_valid, cfi_target, cfi_idx, cfi_type, taken, mispredict, meta):
        @MethodMock.effect
        def eff():
            self.bpu_updates.append(
                {
                    "pc": pc,
                    "branch_mask": branch_mask,
                    "cfi_target": cfi_target,
                    "cfi_idx": cfi_idx,
                    "cfi_type": cfi_type,
                    "taken": taken,
                    "mispredict": mispredict,
                    "meta": meta,
                }
            )

    async def auto_bpu_process(self, sim: ProcessContext):
        while True:
            if self.bpu_requests:
                pc = self.bpu_requests.popleft()
                await self.ftq.bpu_fetch_target.call(sim, pc=pc + 16, ftq_ptr={"ptr": 0, "parity": 0})
            else:
                await sim.tick()

    async def deliver_prediction(self, sim: TestbenchContext, meta: int, pc: int | None = None, ptr: int = 0):
        await self.ftq.bpu_prediction_details.call(
            sim,
            ftq_ptr={"ptr": ptr, "parity": 0},
            pc=self.start_pc if pc is None else pc,
            prediction={},
            meta=meta,
        )

    async def resolve(
        self,
        sim: TestbenchContext,
        cfi_idx: int,
        misprediction: int,
        taken: int,
        cfi_target: int,
        ptr: int = 0,
    ):
        await self.ftq.resolve.call(
            sim,
            ftq_ptr={"ptr": ptr, "parity": 0},
            misprediction=misprediction,
            taken=taken,
            cfi_idx=cfi_idx,
            cfi_type=CfiType.BRANCH,
            cfi_target=cfi_target,
        )

    async def commit_and_get_update(self, sim: TestbenchContext) -> dict:
        await self.ftq.commit.call(sim, ftq_ptr={"ptr": 1, "parity": 0})
        for _ in range(5):
            await sim.tick()
        assert len(self.bpu_updates) == 1
        return self.bpu_updates[0]

    def test_train_sends_resolved_record_after_commit(self):
        async def proc(sim: TestbenchContext):
            await self.deliver_prediction(sim, self.meta)
            await self.resolve(sim, cfi_idx=2, misprediction=0, taken=1, cfi_target=0x180)
            assert len(self.bpu_updates) == 0

            update = await self.commit_and_get_update(sim)
            assert update["pc"] == self.start_pc
            assert update["branch_mask"] == 1 << 2
            assert update["cfi_target"] == 0x180
            assert update["cfi_idx"] == 2
            assert update["cfi_type"] == CfiType.BRANCH
            assert update["taken"] == 1
            assert update["mispredict"] == 0
            assert update["meta"] == self.meta

        with self.run_simulation(self.dut) as sim:
            sim.add_process(self.auto_bpu_process)
            sim.add_testbench(proc)

    def test_train_uses_the_pc_the_prediction_was_made_for(self):
        block_0 = self.start_pc
        block_1 = self.start_pc + self.gen_params.fetch_block_bytes
        meta_0, meta_1 = 0x11, 0x22

        async def proc(sim: TestbenchContext):
            await self.deliver_prediction(sim, meta_0, pc=block_0, ptr=0)
            await self.deliver_prediction(sim, meta_1, pc=block_1, ptr=1)

            await self.resolve(sim, ptr=0, cfi_idx=3, misprediction=1, taken=1, cfi_target=block_1)
            await self.resolve(sim, ptr=1, cfi_idx=0, misprediction=1, taken=1, cfi_target=0x300)

            await self.ftq.commit.call(sim, ftq_ptr={"ptr": 2, "parity": 0})
            for _ in range(5):
                await sim.tick()

            assert len(self.bpu_updates) == 2
            assert self.bpu_updates[0]["pc"] == block_0
            assert self.bpu_updates[0]["meta"] == meta_0
            assert self.bpu_updates[0]["cfi_idx"] == 3
            assert self.bpu_updates[1]["pc"] == block_1
            assert self.bpu_updates[1]["meta"] == meta_1
            assert self.bpu_updates[1]["cfi_idx"] == 0

        with self.run_simulation(self.dut) as sim:
            sim.add_process(self.auto_bpu_process)
            sim.add_testbench(proc)

    def test_unresolved_entry_trains_nothing(self):
        async def proc(sim: TestbenchContext):
            await self.ftq.commit.call(sim, ftq_ptr={"ptr": 1, "parity": 0})
            for _ in range(5):
                await sim.tick()
            assert len(self.bpu_updates) == 0

        with self.run_simulation(self.dut) as sim:
            sim.add_process(self.auto_bpu_process)
            sim.add_testbench(proc)

    def test_resolve_keeps_furthest_cfi_without_mispredict(self):
        async def proc(sim: TestbenchContext):
            await self.resolve(sim, cfi_idx=1, misprediction=0, taken=0, cfi_target=0x180)
            await self.resolve(sim, cfi_idx=0, misprediction=0, taken=0, cfi_target=0x190)
            await self.resolve(sim, cfi_idx=3, misprediction=0, taken=1, cfi_target=0x1A0)

            update = await self.commit_and_get_update(sim)
            assert update["cfi_idx"] == 3
            assert update["branch_mask"] == (1 << 0) | (1 << 1) | (1 << 3)
            assert update["cfi_target"] == 0x1A0
            assert update["taken"] == 1
            assert update["mispredict"] == 0

        with self.run_simulation(self.dut) as sim:
            sim.add_process(self.auto_bpu_process)
            sim.add_testbench(proc)

    def test_resolve_keeps_oldest_mispredicting_cfi(self):
        async def proc(sim: TestbenchContext):
            await self.resolve(sim, cfi_idx=3, misprediction=0, taken=0, cfi_target=0x180)
            await self.resolve(sim, cfi_idx=1, misprediction=1, taken=1, cfi_target=0x300)
            await self.resolve(sim, cfi_idx=2, misprediction=1, taken=1, cfi_target=0x400)
            await self.resolve(sim, cfi_idx=3, misprediction=0, taken=1, cfi_target=0x500)

            update = await self.commit_and_get_update(sim)
            assert update["cfi_idx"] == 1
            assert update["branch_mask"] == 1 << 1
            assert update["cfi_target"] == 0x300
            assert update["taken"] == 1
            assert update["mispredict"] == 1

        with self.run_simulation(self.dut) as sim:
            sim.add_process(self.auto_bpu_process)
            sim.add_testbench(proc)
