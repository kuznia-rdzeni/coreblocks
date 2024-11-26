import random
from coreblocks.func_blocks.fu.lsu.pma import PMAChecker, PMARegion

from transactron.lib import Adapter
from coreblocks.params import GenParams
from coreblocks.func_blocks.fu.lsu.dummyLsu import LSUDummy
from coreblocks.params.configurations import test_core_config
from coreblocks.arch import *
from coreblocks.interface.keys import CoreStateKey, ExceptionReportKey, InstructionPrecommitKey
from transactron.testing.method_mock import MethodMock
from transactron.utils.dependencies import DependencyContext
from coreblocks.interface.layouts import ExceptionRegisterLayouts, RetirementLayouts
from coreblocks.peripherals.wishbone import *
from transactron.testing import TestbenchIO, TestCaseWithSimulator, def_method_mock, TestbenchContext
from coreblocks.peripherals.bus_adapter import WishboneMasterAdapter
from test.peripherals.test_wishbone import WishboneInterfaceWrapper


class TestPMADirect(TestCaseWithSimulator):
    async def verify_region(self, sim: TestbenchContext, region: PMARegion):
        for i in range(region.start, region.end + 1):
            sim.set(self.test_module.addr, i)
            mmio = sim.get(self.test_module.result.mmio)
            assert mmio == region.mmio

    async def process(self, sim: TestbenchContext):
        for r in self.pma_regions:
            await self.verify_region(sim, r)

    def test_pma_direct(self):
        self.pma_regions = [
            PMARegion(0x0, 0xF, False),
            PMARegion(0x10, 0xFF, True),
            PMARegion(0x100, 0x10F, False),
            PMARegion(0x110, 0x120, True),
            PMARegion(0x121, 0x130, False),
        ]

        self.gen_params = GenParams(test_core_config.replace(pma=self.pma_regions))
        self.test_module = PMAChecker(self.gen_params)

        with self.run_simulation(self.test_module) as sim:
            sim.add_testbench(self.process)


class PMAIndirectTestCircuit(Elaboratable):
    def __init__(self, gen: GenParams):
        self.gen = gen

    def elaborate(self, platform):
        m = Module()

        wb_params = WishboneParameters(
            data_width=self.gen.isa.ilen,
            addr_width=32,
        )

        self.bus = WishboneMaster(wb_params)
        self.bus_master_adapter = WishboneMasterAdapter(self.bus)

        m.submodules.exception_report = self.exception_report = TestbenchIO(
            Adapter(i=self.gen.get(ExceptionRegisterLayouts).report)
        )

        DependencyContext.get().add_dependency(ExceptionReportKey(), self.exception_report.adapter.iface)

        layouts = self.gen.get(RetirementLayouts)
        m.submodules.precommit = self.precommit = TestbenchIO(
            Adapter(
                i=layouts.precommit_in,
                o=layouts.precommit_out,
                nonexclusive=True,
                combiner=lambda m, args, runs: args[0],
            ).set(with_validate_arguments=True)
        )
        DependencyContext.get().add_dependency(InstructionPrecommitKey(), self.precommit.adapter.iface)

        m.submodules.core_state = self.core_state = TestbenchIO(Adapter(o=layouts.core_state, nonexclusive=True))
        DependencyContext.get().add_dependency(CoreStateKey(), self.core_state.adapter.iface)

        m.submodules.func_unit = func_unit = LSUDummy(self.gen, self.bus_master_adapter)

        m.submodules.issue_mock = self.issue = TestbenchIO(AdapterTrans(func_unit.issue))
        m.submodules.accept_mock = self.accept = TestbenchIO(AdapterTrans(func_unit.accept))
        self.io_in = WishboneInterfaceWrapper(self.bus.wb_master)
        m.submodules.bus = self.bus
        m.submodules.bus_master_adapter = self.bus_master_adapter
        return m


class TestPMAIndirect(TestCaseWithSimulator):
    def get_instr(self, addr):
        return {
            "rp_dst": 1,
            "rob_id": 1,
            "exec_fn": {"op_type": OpType.LOAD, "funct3": Funct3.B, "funct7": 0},
            "s1_val": 0,
            "s2_val": 1,
            "imm": addr,
            "pc": 0,
        }

    async def verify_region(self, sim: TestbenchContext, region: PMARegion):
        for addr in range(region.start, region.end + 1):
            instr = self.get_instr(addr)
            await self.test_module.issue.call(sim, instr)
            if region.mmio is True:
                wb = self.test_module.io_in.wb
                for i in range(100):  # 100 cycles is more than enough
                    wb_requested = sim.get(wb.stb) and sim.get(wb.cyc)
                    assert not wb_requested

            await self.test_module.io_in.slave_wait(sim)
            await self.test_module.io_in.slave_respond(sim, (addr << (addr % 4) * 8))
            v = await self.test_module.accept.call(sim)
            assert v.result == addr

    async def process(self, sim: TestbenchContext):
        for region in self.pma_regions:
            await self.verify_region(sim, region)

    def test_pma_indirect(self):
        self.pma_regions = [
            PMARegion(0x0, 0xF, True),
            PMARegion(0x10, 0x1F, False),
            PMARegion(0x20, 0x2F, True),
        ]
        self.gen_params = GenParams(test_core_config.replace(pma=self.pma_regions))
        self.test_module = PMAIndirectTestCircuit(self.gen_params)

        @def_method_mock(lambda: self.test_module.exception_report)
        def exception_consumer(arg):
            @MethodMock.effect
            def eff():
                assert False

        @def_method_mock(
            lambda: self.test_module.precommit,
            validate_arguments=lambda rob_id: rob_id == 1,
            enable=lambda: random.random() < 0.5,
        )
        def precommiter(rob_id):
            return {"side_fx": 1}

        @def_method_mock(lambda: self.test_module.core_state)
        def core_state_process():
            return {"flushing": 0}

        with self.run_simulation(self.test_module) as sim:
            sim.add_testbench(self.process)
