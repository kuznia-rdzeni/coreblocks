import random
import pytest
from transactron.testing import TestCaseWithSimulator, SimpleTestCircuit, TestbenchContext

from coreblocks.core_structs.rf import RegisterFile
from coreblocks.params import GenParams
from coreblocks.params.configurations import test_core_config


class TestRegisterFile(TestCaseWithSimulator):
    def tb_read_req(self, k: int):
        async def tb(sim: TestbenchContext):
            pass

        return tb

    def tb_read_resp(self, k: int):
        async def tb(sim: TestbenchContext):
            pass

        return tb

    def tb_write(self, k: int):
        async def tb(sim: TestbenchContext):
            for _ in range(self.num_writes):
                while not any(self.free_regs):
                    await sim.tick()
                reg_id = random.choice([reg_id for reg_id, free in enumerate(self.free_regs) if free])
                reg_val = random.randrange(0, 2**self.gen_params.isa.xlen)
                self.free_regs[reg_id] = False
                await self.m.write[k].call(sim, reg_id=reg_id, reg_val=reg_val)
                self.reg_values[k] = reg_val
                self.reg_valids[reg_id] = True

        return tb

    def tb_free(self, k: int):
        async def tb(sim: TestbenchContext):
            while True:
                while not any(self.reg_valids):
                    await sim.tick()
                reg_id = random.choice([reg_id for reg_id, valid in enumerate(self.reg_valids) if valid])
                self.reg_valids[reg_id] = False
                await self.m.free[k].call(sim, reg_id=reg_id)
                self.free_regs[reg_id] = True

        return tb

    @pytest.mark.parametrize("read_ports, write_ports, free_ports", [(2, 1, 1), (4, 2, 2)])
    def test_randomized(self, read_ports: int, write_ports: int, free_ports: int):
        self.gen_params = GenParams(test_core_config)
        self.m = m = SimpleTestCircuit(
            RegisterFile(
                gen_params=self.gen_params, read_ports=read_ports, write_ports=write_ports, free_ports=free_ports
            )
        )
        self.num_writes = 1000

        self.reg_values = [0 for _ in range(self.gen_params.phys_regs)]
        self.reg_valids = [False for _ in range(self.gen_params.phys_regs)]
        self.free_regs = [True for _ in range(self.gen_params.phys_regs)]

        random.seed(42)

        with self.run_simulation(m) as sim:
            for k in range(read_ports):
                sim.add_testbench(self.tb_read_req(k), background=True)
                sim.add_testbench(self.tb_read_resp(k), background=True)
            for k in range(write_ports):
                sim.add_testbench(self.tb_write(k))
            for k in range(free_ports):
                sim.add_testbench(self.tb_free(k), background=True)
