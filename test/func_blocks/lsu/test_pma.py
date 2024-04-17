from amaranth.sim import Settle
from coreblocks.func_blocks.fu.lsu.pma import PMAChecker, PMARegion

from transactron.lib import Adapter
from coreblocks.params import GenParams
from coreblocks.func_blocks.fu.lsu.dummyLsu import LSUDummy
from coreblocks.params.configurations import test_core_config
from coreblocks.frontend.decoder import *
from coreblocks.interface.keys import ExceptionReportKey, InstructionPrecommitKey
from transactron.utils.dependencies import DependencyManager
from coreblocks.interface.layouts import ExceptionRegisterLayouts, RetirementLayouts
from coreblocks.peripherals.wishbone import *
from transactron.testing import TestbenchIO, TestCaseWithSimulator, def_method_mock
from coreblocks.peripherals.bus_adapter import WishboneMasterAdapter
from test.peripherals.test_wishbone import WishboneInterfaceWrapper


class TestPMADirect(TestCaseWithSimulator):
    def verify_region(self, region: PMARegion):
        for i in range(region.start, region.end + 1):
            yield self.test_module.addr.eq(i)
            yield Settle()
            mmio = yield self.test_module.result["mmio"]
            assert mmio == region.mmio

    def process(self):
        for r in self.pma_regions:
            yield from self.verify_region(r)

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
            sim.add_sync_process(self.process)


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

        self.gen.get(DependencyManager).add_dependency(ExceptionReportKey(), self.exception_report.adapter.iface)

        m.submodules.precommit = self.precommit = TestbenchIO(
            Adapter(o=self.gen.get(RetirementLayouts).precommit, nonexclusive=True)
        )
        self.gen.get(DependencyManager).add_dependency(InstructionPrecommitKey(), self.precommit.adapter.iface)

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

    def verify_region(self, region: PMARegion):
        for addr in range(region.start, region.end + 1):
            instr = self.get_instr(addr)
            yield from self.test_module.issue.call(instr)
            if region.mmio is True:
                wb = self.test_module.io_in.wb
                for i in range(100):  # 100 cycles is more than enough
                    wb_requested = (yield wb.stb) and (yield wb.cyc)
                    assert not wb_requested

                yield from self.test_module.precommit.call(rob_id=1, side_fx=1)

            yield from self.test_module.io_in.slave_wait()
            yield from self.test_module.io_in.slave_respond((addr << (addr % 4) * 8))
            yield Settle()
            v = yield from self.test_module.accept.call()
            assert v["result"] == addr

    def process(self):
        for region in self.pma_regions:
            yield from self.verify_region(region)

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
            assert False

        with self.run_simulation(self.test_module) as sim:
            sim.add_sync_process(self.process)
