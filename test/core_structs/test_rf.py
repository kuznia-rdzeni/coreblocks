import random
from typing import Optional
import pytest
from collections import deque
from transactron.testing import TestCaseWithSimulator, SimpleTestCircuit, TestbenchContext

from coreblocks.core_structs.rf import RegisterFile
from coreblocks.params import GenParams
from coreblocks.params.configurations import test_core_config


class TestRegisterFile(TestCaseWithSimulator):
    def tb_read_req(self, k: int):
        async def tb(sim: TestbenchContext):
            while True:
                await self.random_wait_geom(sim, 0.95)
                reg_id = random.randrange(0, self.gen_params.phys_regs)
                await self.m.read_req[k].call(sim, reg_id=reg_id)
                self.read_queues[k].append(reg_id)

        return tb

    def tb_read_resp(self, k: int):
        async def tb(sim: TestbenchContext):
            await sim.delay(1e-9)
            while True:
                # TODO: currently RF requires response to happen a cycle after request
                # await self.random_wait_geom(sim, 0.95)
                while not self.read_queues[k]:
                    await sim.tick()
                    await sim.delay(1e-9)
                reg_id = self.read_queues[k].popleft()
                resp = await self.m.read_resp[k].call(sim, reg_id=reg_id)
                await sim.delay(1e-9)  # writes happen before asserts
                assert bool(resp.valid) == (self.reg_values[reg_id] is not None)
                assert self.reg_values[reg_id] is None or resp.reg_val == self.reg_values[reg_id]

        return tb

    def tb_write(self, k: int):
        async def tb(sim: TestbenchContext):
            for _ in range(self.num_writes):
                await self.random_wait_geom(sim, 0.8)
                await sim.delay(1e-9)
                while not self.free_set:
                    await sim.tick()
                    await sim.delay(1e-9)
                reg_id = random.choice(list(self.free_set))
                self.free_set.remove(reg_id)
                reg_val = random.randrange(0, 2**self.gen_params.isa.xlen)
                await self.m.write[k].call(sim, reg_id=reg_id, reg_val=reg_val)
                self.used_set.add(reg_id)
                self.reg_values[reg_id] = reg_val

        return tb

    def tb_free(self, k: int):
        async def tb(sim: TestbenchContext):
            await sim.delay(2e-9)
            while True:
                await self.random_wait_geom(sim, 0.5)
                await sim.delay(2e-9)
                while not self.used_set:
                    await sim.tick()
                    await sim.delay(2e-9)
                reg_id = random.choice(list(self.used_set))
                self.used_set.remove(reg_id)
                await self.m.free[k].call(sim, reg_id=reg_id)
                await sim.delay(2e-9)  # frees happen after asserts
                self.free_set.add(reg_id)
                self.reg_values[reg_id] = None

        return tb

    @pytest.mark.parametrize("read_ports, write_ports, free_ports", [(2, 1, 1), (4, 2, 2)])
    def test_randomized(self, read_ports: int, write_ports: int, free_ports: int):
        self.gen_params = GenParams(test_core_config.replace(phys_regs_bits=4))
        self.m = m = SimpleTestCircuit(
            RegisterFile(
                gen_params=self.gen_params, read_ports=read_ports, write_ports=write_ports, free_ports=free_ports
            )
        )
        self.num_writes = 1000

        self.reg_values: list[Optional[int]] = [None for _ in range(self.gen_params.phys_regs)]
        self.reg_values[0] = 0

        self.read_queues: list[deque[int]] = [deque() for _ in range(read_ports)]
        self.free_set: set[int] = set(range(1, self.gen_params.phys_regs))
        self.used_set: set[int] = set()

        random.seed(42)

        with self.run_simulation(m) as sim:
            for k in range(read_ports):
                sim.add_testbench(self.tb_read_req(k), background=True)
                sim.add_testbench(self.tb_read_resp(k), background=True)
            for k in range(write_ports):
                sim.add_testbench(self.tb_write(k))
            for k in range(free_ports):
                sim.add_testbench(self.tb_free(k), background=True)
