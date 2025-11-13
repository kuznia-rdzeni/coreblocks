from collections import deque
import random

from coreblocks.backend.announcement import ResultAnnouncement
from coreblocks.params import GenParams
from coreblocks.params.configurations import test_core_config
from transactron.testing import CallTrigger, SimpleTestCircuit, TestCaseWithSimulator, TestbenchContext


class TestResultAnnouncement(TestCaseWithSimulator):
    async def producer(self, sim: TestbenchContext):
        for _ in range(self.num_cases):
            rob_id = random.randrange(2**self.gen_params.rob_entries_bits)
            result = random.randrange(2**self.gen_params.isa.xlen)
            rp_dst = random.randrange(2**self.gen_params.phys_regs_bits)
            exception = random.randrange(2)
            self.queue.append((rob_id, result, rp_dst, exception))
            await self.m.push_result.call(sim, rob_id=rob_id, result=result, rp_dst=rp_dst, exception=exception)
            await self.random_wait_geom(sim, 0.5)

    async def consumer(self, sim: TestbenchContext):
        for _ in range(self.num_cases):
            rob_result, rs_result, rf_result = (
                await CallTrigger(sim)
                .call(self.m.rob_mark_done)
                .call(self.m.rs_update)
                .call(self.m.rf_write_val)
                .until_done()
            )

            assert rf_result is not None
            assert rs_result is not None or rf_result.reg_id == 0
            assert rob_result is not None

            if rs_result is not None:
                assert rf_result.reg_val == rs_result.reg_val
                assert rf_result.reg_id == rs_result.reg_id

            (rob_id, result, rp_dst, exception) = self.queue.popleft()

            assert rob_id == rob_result.rob_id
            assert result == rf_result.reg_val
            assert rp_dst == rf_result.reg_id
            assert exception == rob_result.exception

            await self.random_wait_geom(sim, 0.5)

    def test_result_announcement(self):
        self.gen_params = GenParams(test_core_config)
        self.m = SimpleTestCircuit(ResultAnnouncement(gen_params=self.gen_params))
        self.queue = deque()
        self.num_cases = 100
        random.seed(14)

        with self.run_simulation(self.m) as sim:
            sim.add_testbench(self.producer)
            sim.add_testbench(self.consumer)
