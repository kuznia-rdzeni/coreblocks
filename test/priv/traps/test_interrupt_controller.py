from transactron.testing import SimpleTestCircuit, TestCaseWithSimulator, TestbenchContext
from transactron.utils import ModuleConnector
from transactron.utils.dependencies import DependencyContext

from coreblocks.arch import InterruptCauseNumber, PrivilegeLevel
from coreblocks.arch.isa_consts import ExceptionCause
from coreblocks.interface.keys import CSRInstancesKey
from coreblocks.params import GenParams
from coreblocks.params import configurations
from coreblocks.priv.csr.csr_instances import CSRInstances
from coreblocks.priv.traps.interrupt_controller import InternalInterruptController

import pytest


class TestInterruptControllerSModeTraps(TestCaseWithSimulator):
    @pytest.fixture(autouse=True)
    def setup_method(self):
        self.gen_params = GenParams(configurations.test.replace(supervisor_mode=True, xlen=64, fetch_block_bytes_log=3))
        self.csr_instances = CSRInstances(self.gen_params)
        DependencyContext.get().add_dependency(CSRInstancesKey(), self.csr_instances)
        self.ic = InternalInterruptController(self.gen_params)
        self.tc = SimpleTestCircuit(self.ic)
        self.dut = ModuleConnector(ic=self.tc, csr_instances=self.csr_instances)

    async def entry_to_supervisor_process(self, sim: TestbenchContext):
        illegal_instruction = int(ExceptionCause.ILLEGAL_INSTRUCTION)

        sim.set(self.csr_instances.m_mode.priv_mode.value, PrivilegeLevel.USER)
        sim.set(self.ic.mstatus_sie.value, 1)
        sim.set(self.ic.medeleg.value, 1 << illegal_instruction)
        await sim.tick()

        entry = await self.tc.entry.call(sim, cause=illegal_instruction)
        assert entry["target_priv"] == PrivilegeLevel.SUPERVISOR
        await sim.tick()

        assert sim.get(self.csr_instances.m_mode.priv_mode.value) == PrivilegeLevel.SUPERVISOR
        assert sim.get(self.ic.mstatus_sie.value) == 0
        assert sim.get(self.ic.mstatus_spie.value) == 1
        assert sim.get(self.ic.mstatus_spp.value) == 0

    async def entry_to_delegated_exception_does_not_reduce_privilege_process(self, sim: TestbenchContext):
        illegal_instruction = int(ExceptionCause.ILLEGAL_INSTRUCTION)

        sim.set(self.csr_instances.m_mode.priv_mode.value, PrivilegeLevel.MACHINE)
        sim.set(self.ic.mstatus_mie.value, 1)
        sim.set(self.ic.medeleg.value, 1 << illegal_instruction)
        await sim.tick()

        entry = await self.tc.entry.call(sim, cause=illegal_instruction)
        assert entry["target_priv"] == PrivilegeLevel.MACHINE
        await sim.tick()

        assert sim.get(self.csr_instances.m_mode.priv_mode.value) == PrivilegeLevel.MACHINE
        assert sim.get(self.ic.mstatus_mie.value) == 0
        assert sim.get(self.ic.mstatus_mpie.value) == 1
        assert sim.get(self.ic.mstatus_mpp.value) == PrivilegeLevel.MACHINE

    async def sret_restores_mode_and_interrupts_process(self, sim: TestbenchContext):
        sim.set(self.csr_instances.m_mode.priv_mode.value, PrivilegeLevel.SUPERVISOR)
        sim.set(self.ic.mstatus_sie.value, 0)
        sim.set(self.ic.mstatus_spie.value, 1)
        sim.set(self.ic.mstatus_spp.value, 0)
        await sim.tick()

        await self.tc.sret.call(sim)
        await sim.tick()

        assert sim.get(self.csr_instances.m_mode.priv_mode.value) == PrivilegeLevel.USER
        assert sim.get(self.ic.mstatus_sie.value) == 1
        assert sim.get(self.ic.mstatus_spie.value) == 1
        assert sim.get(self.ic.mstatus_spp.value) == 0

    async def machine_interrupt_priority_over_supervisor_process(self, sim: TestbenchContext):
        mei = int(InterruptCauseNumber.MEI)
        sei = int(InterruptCauseNumber.SEI)

        sim.set(self.csr_instances.m_mode.priv_mode.value, PrivilegeLevel.MACHINE)
        sim.set(self.ic.mstatus_mie.value, 1)
        sim.set(self.ic.mstatus_sie.value, 1)
        sim.set(self.ic.mie.value, (1 << mei) | (1 << sei))
        sim.set(self.ic.mideleg.value, 1 << sei)
        sim.set(self.ic.internal_report_level, (1 << mei) | (1 << sei))

        for _ in range(8):
            await sim.tick()
            if sim.get(self.ic.interrupt_insert):
                break

        assert sim.get(self.ic.interrupt_insert) == 1
        await sim.tick()
        cause = await self.tc.interrupt_cause.call(sim)
        assert cause["cause"] == mei

    def test_entry_to_supervisor(self):
        with self.run_simulation(self.dut) as sim:
            sim.add_testbench(self.entry_to_supervisor_process)

    def test_entry_to_delegated_exception_does_not_reduce_privilege(self):
        with self.run_simulation(self.dut) as sim:
            sim.add_testbench(self.entry_to_delegated_exception_does_not_reduce_privilege_process)

    def test_sret_restores_mode_and_interrupts(self):
        with self.run_simulation(self.dut) as sim:
            sim.add_testbench(self.sret_restores_mode_and_interrupts_process)

    def test_machine_interrupt_priority_over_supervisor(self):
        with self.run_simulation(self.dut) as sim:
            sim.add_testbench(self.machine_interrupt_priority_over_supervisor_process)
