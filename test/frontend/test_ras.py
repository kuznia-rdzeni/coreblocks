import pytest

from transactron.testing import (
    TestCaseWithSimulator,
    SimpleTestCircuit,
    TestbenchContext,
)

from coreblocks.frontend.bpu.ras import RAS
from coreblocks.params import BranchPredictionConfig, GenParams, RASConfig
from coreblocks.params import configurations


class TestRAS(TestCaseWithSimulator):
    @pytest.fixture(autouse=True)
    def setup(self, fixture_initialize_testing_env):
        self.config = RASConfig(entries_log=2)
        self.gen_params = GenParams(configurations.test.replace(bpu_config=BranchPredictionConfig(ras=self.config)))
        self.depth = 2**self.config.entries_log
        self.ras = SimpleTestCircuit(RAS(self.gen_params, self.config))

    async def push(self, sim: TestbenchContext, addr: int):
        return await self.ras.update.call(sim, push=1, pop=0, addr=addr)

    async def pop(self, sim: TestbenchContext):
        return await self.ras.update.call(sim, push=0, pop=1, addr=0)

    async def recover(self, sim: TestbenchContext, checkpoint):
        return await self.ras.recover.call(sim, sp=checkpoint["sp"], count=checkpoint["count"], top=checkpoint["top"])

    def test_empty_stack_has_no_top(self):
        async def proc(sim: TestbenchContext):
            assert (await self.ras.peek.call(sim))["valid"] == 0

        with self.run_simulation(self.ras) as sim:
            sim.add_testbench(proc)

    def test_calls_return_in_reverse_order(self):
        addrs = [0x1000, 0x2000, 0x3000]

        async def proc(sim: TestbenchContext):
            for addr in addrs:
                await self.push(sim, addr)

            for addr in reversed(addrs):
                res = await self.ras.peek.call(sim)
                assert res["valid"] == 1
                assert res["addr"] == addr
                await self.pop(sim)

            assert (await self.ras.peek.call(sim))["valid"] == 0

        with self.run_simulation(self.ras) as sim:
            sim.add_testbench(proc)

    def test_push_and_pop_replaces_the_top(self):
        async def proc(sim: TestbenchContext):
            await self.push(sim, 0x1000)
            await self.push(sim, 0x2000)

            await self.ras.update.call(sim, push=1, pop=1, addr=0x3000)

            assert (await self.ras.peek.call(sim))["addr"] == 0x3000
            await self.pop(sim)
            assert (await self.ras.peek.call(sim))["addr"] == 0x1000

        with self.run_simulation(self.ras) as sim:
            sim.add_testbench(proc)

    def test_popping_an_empty_stack_stays_empty(self):
        async def proc(sim: TestbenchContext):
            for _ in range(3):
                await self.pop(sim)
                assert (await self.ras.peek.call(sim))["valid"] == 0

            await self.push(sim, 0x1000)
            res = await self.ras.peek.call(sim)
            assert res["valid"] == 1
            assert res["addr"] == 0x1000

        with self.run_simulation(self.ras) as sim:
            sim.add_testbench(proc)

    def test_overflow_wraps_and_keeps_the_newest(self):
        addrs = [0x1000 * (i + 1) for i in range(self.depth + 2)]

        async def proc(sim: TestbenchContext):
            for addr in addrs:
                await self.push(sim, addr)

            for addr in reversed(addrs[-self.depth :]):
                assert (await self.ras.peek.call(sim))["addr"] == addr
                await self.pop(sim)

            assert (await self.ras.peek.call(sim))["valid"] == 0

        with self.run_simulation(self.ras) as sim:
            sim.add_testbench(proc)

    def test_recover_undoes_a_wrong_path_call(self):
        async def proc(sim: TestbenchContext):
            await self.push(sim, 0x1000)
            checkpoint = await self.push(sim, 0x2000)

            await self.push(sim, 0xDEAD)

            await self.recover(sim, checkpoint)

            assert (await self.ras.peek.call(sim))["addr"] == 0x2000
            await self.pop(sim)
            assert (await self.ras.peek.call(sim))["addr"] == 0x1000

        with self.run_simulation(self.ras) as sim:
            sim.add_testbench(proc)

    def test_recover_restores_the_top_entry(self):
        async def proc(sim: TestbenchContext):
            checkpoint = await self.push(sim, 0x1000)

            await self.ras.update.call(sim, push=1, pop=1, addr=0xDEAD)
            assert (await self.ras.peek.call(sim))["addr"] == 0xDEAD

            await self.recover(sim, checkpoint)

            res = await self.ras.peek.call(sim)
            assert res["valid"] == 1
            assert res["addr"] == 0x1000

        with self.run_simulation(self.ras) as sim:
            sim.add_testbench(proc)
