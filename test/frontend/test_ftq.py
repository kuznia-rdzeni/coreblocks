import pytest
from collections import deque

from transactron.testing import (
    TestCaseWithSimulator,
    def_method_mock,
    SimpleTestCircuit,
    TestbenchContext,
    ProcessContext,
)
from transactron.testing.method_mock import MethodMock

from coreblocks.frontend.ftq import FetchTargetQueue
from coreblocks.params import GenParams
from coreblocks.params import configurations


class TestFetchTargetQueue(TestCaseWithSimulator):
    @pytest.fixture(autouse=True)
    def setup(self, fixture_initialize_testing_env):
        self.start_pc = 0x100
        self.gen_params = GenParams(configurations.test.replace(start_pc=self.start_pc))
        self.ifu_requests: deque = deque()
        self.bpu_requests: deque = deque()
        self.bpu_flush_count: int = 0

        self.ftq = SimpleTestCircuit(FetchTargetQueue(self.gen_params))

    @def_method_mock(lambda self: self.ftq.stall_guard)
    def stall_guard_mock(self):
        pass

    @def_method_mock(lambda self: self.ftq.bpu_flush)
    def bpu_flush_mock(self):
        @MethodMock.effect
        def eff():
            self.bpu_flush_count += 1

    @def_method_mock(lambda self: self.ftq.bpu_request)
    def bpu_request_mock(self, pc, ftq_ptr):
        @MethodMock.effect
        def eff():
            self.bpu_requests.append(pc)

    @def_method_mock(lambda self: self.ftq.ifu_request)
    def ifu_request_mock(self, pc, ftq_ptr, fetch_gen):
        @MethodMock.effect
        def eff():
            self.ifu_requests.append({"pc": pc, "ftq_ptr": ftq_ptr["ptr"]})

    async def auto_bpu_process(self, sim: ProcessContext):
        """Responds to each BPU request by predicting PC+4 as the next PC."""
        while True:
            if self.bpu_requests:
                pc = self.bpu_requests.popleft()
                await self.ftq.bpu_response.call(sim, pc=pc + 4, ftq_ptr={"ptr": 0, "parity": 0})
            else:
                await sim.tick()

    def test_alloc_sends_ifu_request_with_start_pc(self):
        async def proc(sim: TestbenchContext):
            for _ in range(5):
                await sim.tick()
            assert len(self.ifu_requests) >= 1
            assert self.ifu_requests[0]["pc"] == self.start_pc
            assert self.ifu_requests[0]["ftq_ptr"] == 0

        with self.run_simulation(self.ftq) as sim:
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

        with self.run_simulation(self.ftq) as sim:
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

        with self.run_simulation(self.ftq) as sim:
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

        with self.run_simulation(self.ftq) as sim:
            sim.add_testbench(proc)

    def test_backend_redirect_restarts_fetch_from_new_pc(self):
        # backend_redirect calls FAU.backend_redirect which sets the new PC directly.
        redirect_pc = 0x400

        async def proc(sim: TestbenchContext):
            await self.ftq.backend_redirect.call(sim, pc=redirect_pc)
            for _ in range(5):
                await sim.tick()
            assert redirect_pc in [req["pc"] for req in self.ifu_requests]

        with self.run_simulation(self.ftq) as sim:
            sim.add_testbench(proc)


class TestFetchTargetQueueFull(TestCaseWithSimulator):
    @pytest.fixture(autouse=True)
    def setup(self, fixture_initialize_testing_env):
        self.start_pc = 0x100
        # small FTQ (4 entries) to exercise the full condition quickly
        self.gen_params = GenParams(configurations.test.replace(start_pc=self.start_pc, ftq_size_log=2))
        self.ifu_requests: deque = deque()
        self.bpu_requests: deque = deque()

        self.ftq = SimpleTestCircuit(FetchTargetQueue(self.gen_params))

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
        @MethodMock.effect
        def eff():
            self.ifu_requests.append(pc)

    async def auto_bpu_process(self, sim: ProcessContext):
        while True:
            if self.bpu_requests:
                pc = self.bpu_requests.popleft()
                await self.ftq.bpu_response.call(sim, pc=pc + 4, ftq_ptr={"ptr": 0, "parity": 0})
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

        with self.run_simulation(self.ftq) as sim:
            sim.add_process(self.auto_bpu_process)
            sim.add_testbench(proc)
