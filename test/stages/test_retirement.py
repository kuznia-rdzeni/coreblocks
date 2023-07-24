from coreblocks.params.layouts import ExceptionRegisterLayouts
from coreblocks.stages.retirement import *
from coreblocks.structs_common.csr_generic import GenericCSRRegisters

from coreblocks.transactions.lib import FIFO, Adapter
from coreblocks.structs_common.rat import RRAT
from coreblocks.params import ROBLayouts, RFLayouts, GenParams, LSULayouts, SchedulerLayouts
from coreblocks.params.configurations import test_core_config

from ..common import *
from ..transactional_testing import Exit, Sim, SimFIFO, SimSignal, Wait
import random


class RetirementTestCircuit(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params

    def elaborate(self, platform):
        m = Module()

        rob_layouts = self.gen_params.get(ROBLayouts)
        rf_layouts = self.gen_params.get(RFLayouts)
        lsu_layouts = self.gen_params.get(LSULayouts)
        scheduler_layouts = self.gen_params.get(SchedulerLayouts)
        exception_layouts = self.gen_params.get(ExceptionRegisterLayouts)

        m.submodules.r_rat = self.rat = RRAT(gen_params=self.gen_params)
        m.submodules.free_rf_list = self.free_rf = FIFO(
            scheduler_layouts.free_rf_layout, 2**self.gen_params.phys_regs_bits
        )

        m.submodules.mock_rob_peek = self.mock_rob_peek = Adapter(o=rob_layouts.peek_layout)

        m.submodules.mock_rob_retire = self.mock_rob_retire = Adapter(o=rob_layouts.retire_layout)

        m.submodules.mock_rf_free = self.mock_rf_free = Adapter(i=rf_layouts.rf_free)

        m.submodules.mock_precommit = self.mock_precommit = Adapter(i=lsu_layouts.precommit)

        m.submodules.mock_exception_cause = self.mock_exception_cause = Adapter(o=exception_layouts.get)
        m.submodules.generic_csr = self.generic_csr = GenericCSRRegisters(self.gen_params)
        self.gen_params.get(DependencyManager).add_dependency(GenericCSRRegistersKey(), self.generic_csr)

        m.submodules.retirement = self.retirement = Retirement(
            self.gen_params,
            rob_retire=self.mock_rob_retire.iface,
            rob_peek=self.mock_rob_peek.iface,
            r_rat_commit=self.rat.commit,
            free_rf_put=self.free_rf.write,
            rf_free=self.mock_rf_free.iface,
            precommit=self.mock_precommit.iface,
            exception_cause_get=self.mock_exception_cause.iface,
        )

        m.submodules.free_rf_fifo_adapter = self.free_rf_adapter = AdapterTrans(self.free_rf.read)

        return m


class RetirementTest(TestCaseWithSimulator):
    def setUp(self):
        self.gen_params = GenParams(test_core_config)
        self.rf_exp_q = SimFIFO()
        self.rat_map_q = SimFIFO()
        self.submit_q = SimFIFO()
        self.rf_free_q = SimFIFO()
        self.precommit_q = SimFIFO()

        random.seed(8)
        self.cycles = 256

        rat_state = [0] * self.gen_params.isa.reg_cnt

        for _ in range(self.cycles):
            rl = random.randrange(self.gen_params.isa.reg_cnt)
            rp = random.randrange(1, 2**self.gen_params.phys_regs_bits) if rl != 0 else 0
            rob_id = random.randrange(2**self.gen_params.rob_entries_bits)
            if rl != 0:
                if rat_state[rl] != 0:  # phys reg 0 shouldn't be marked as free
                    self.rf_exp_q.init_push(rat_state[rl])
                self.rf_free_q.init_push(rat_state[rl])
                rat_state[rl] = rp
                self.rat_map_q.init_push({"rl_dst": rl, "rp_dst": rp})
                self.submit_q.init_push({"rob_data": {"rl_dst": rl, "rp_dst": rp}, "rob_id": rob_id, "exception": 0})
                self.precommit_q.init_push(rob_id)
            # note: overwriting with the same rp or having duplicate nonzero rps in rat shouldn't happen in reality
            # (and the retirement code doesn't have any special behaviour to handle these cases), but in this simple
            # test we don't care to make sure that the randomly generated inputs are correct in this way.

    def test_rand(self):
        retc = RetirementTestCircuit(self.gen_params)

        @Sim.def_method_mock(lambda: retc.mock_rob_retire, enable=self.submit_q.not_empty)
        async def retire_process():
            return await self.submit_q.pop()

        # TODO: mocking really seems to dislike nonexclusive methods for some reason
        @Sim.def_method_mock(lambda: retc.mock_rob_peek, enable=self.submit_q.not_empty)
        async def peek_process():
            return await self.submit_q.peek()

        async def free_reg_process():
            if await self.rf_exp_q.not_empty():
                reg = await Sim.call(retc.free_rf_adapter)
                await Wait()
                self.assertEqual(reg["reg_id"], await self.rf_exp_q.pop())
            else:
                await Exit()

        wait_cycles = SimSignal(0)

        # this test waits for next rat pair to be correctly set and will timeout if that assignment fails
        async def rat_process():
            nonlocal wait_cycles
            if await self.rat_map_q.not_empty():
                current_map = await self.rat_map_q.peek()
                val = await Sim.get(retc.rat.entries[current_map["rl_dst"]])
                await Wait()
                if val == current_map["rp_dst"]:
                    await self.rat_map_q.pop()
                    await wait_cycles.set_final(0)
                else:
                    await wait_cycles.set_final(await wait_cycles.get())
                    if await wait_cycles.get() >= self.cycles + 10:
                        self.fail("RAT entry was not updated")
            else:
                self.assertFalse(await self.submit_q.not_empty())
                self.assertFalse(await self.rf_free_q.not_empty())
                await Exit()

        @Sim.def_method_mock(lambda: retc.mock_rf_free)
        async def rf_free_process(reg_id):
            await Wait()
            self.assertEqual(reg_id, await self.rf_free_q.pop())

        @Sim.def_method_mock(lambda: retc.mock_precommit)
        async def precommit_process(rob_id):
            await Wait()
            self.assertEqual(rob_id, await self.precommit_q.pop())

        @Sim.def_method_mock(lambda: retc.mock_exception_cause)
        async def exception_cause_process():
            return {"cause": 0, "rob_id": 0}  # keep exception cause method enabled

        with self.run_simulation(retc) as sim:
            tsim = Sim()
            tsim.add_process(retire_process)
            tsim.add_process(peek_process)
            tsim.add_process(rf_free_process)
            tsim.add_process(precommit_process)
            tsim.add_process(exception_cause_process)
            tsim.add_process(free_reg_process)
            tsim.add_process(rat_process)
            sim.add_sync_process(tsim.process)
