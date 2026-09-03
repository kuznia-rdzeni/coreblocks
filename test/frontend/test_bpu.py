import pytest
from collections import deque

from transactron.testing import (
    TestCaseWithSimulator,
    SimpleTestCircuit,
    TestbenchContext,
    def_method_mock,
)
from transactron.testing.method_mock import MethodMock

from coreblocks.arch import CfiType
from coreblocks.frontend.bpu.bpu import BranchPredictionUnit
from coreblocks.params import GenParams
from coreblocks.params import configurations


class TestBranchPredictionUnit(TestCaseWithSimulator):
    @pytest.fixture(autouse=True)
    def setup(self, fixture_initialize_testing_env):
        # A multi-instruction fetch block, so in-block CFI indices are meaningful
        self.gen_params = GenParams(configurations.test.replace(fetch_block_bytes_log=4))
        self.fbl = self.gen_params.fetch_block_bytes_log
        self.bpu = SimpleTestCircuit(BranchPredictionUnit(self.gen_params))
        self.predictions: deque = deque()

    def fall_through(self, pc: int) -> int:
        return ((pc >> self.fbl) + 1) << self.fbl

    @def_method_mock(lambda self: self.bpu.write_prediction)
    def write_prediction_mock(self, pc, ftq_ptr, prediction):
        @MethodMock.effect
        def eff():
            self.predictions.append(pc)

    async def predict(self, sim: TestbenchContext, pc: int) -> int:
        self.predictions.clear()
        await self.bpu.request.call(sim, pc=pc, ftq_ptr={"ptr": 0, "parity": 0})
        while not self.predictions:
            await sim.tick()
        return self.predictions[-1]

    def test_unknown_block_falls_through(self):
        pc = 0x100

        async def proc(sim: TestbenchContext):
            assert await self.predict(sim, pc) == self.fall_through(pc)

        with self.run_simulation(self.bpu) as sim:
            sim.add_testbench(proc)

    def test_learned_taken_branch_redirects_to_target(self):
        pc = 0x100
        target = 0x2ABC

        async def proc(sim: TestbenchContext):
            assert await self.predict(sim, pc) == self.fall_through(pc)

            await self.bpu.update.call(sim, pc=pc, cfi_target=target, cfi_idx=0, cfi_type=CfiType.BRANCH, taken=1)

            assert await self.predict(sim, pc) == target

        with self.run_simulation(self.bpu) as sim:
            sim.add_testbench(proc)

    def test_not_taken_update_does_not_redirect(self):
        pc = 0x100

        async def proc(sim: TestbenchContext):
            await self.bpu.update.call(sim, pc=pc, cfi_target=0xDEAD, cfi_idx=0, cfi_type=CfiType.BRANCH, taken=0)
            assert await self.predict(sim, pc) == self.fall_through(pc)

        with self.run_simulation(self.bpu) as sim:
            sim.add_testbench(proc)
