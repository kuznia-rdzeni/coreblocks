from amaranth.sim import Settle
from coreblocks.lsu.pma import PMAChecker, PMARegion

from transactron.lib import Adapter
from coreblocks.params import OpType, GenParams
from coreblocks.lsu.dummyLsu import LSUDummy
from coreblocks.params.configurations import test_core_config
from coreblocks.params.isa import *
from coreblocks.params.keys import ExceptionReportKey
from transactron.utils.dependencies import DependencyManager
from coreblocks.params.layouts import ExceptionRegisterLayouts
from coreblocks.peripherals.wishbone import *
from test.common import TestbenchIO, def_method_mock
from test.coreblocks_test_case import CoreblocksTestCaseWithSimulator
from test.peripherals.test_wishbone import WishboneInterfaceWrapper


class TestPMADirect(CoreblocksTestCaseWithSimulator):
    def verify_region(self, region: PMARegion):
        for i in range(region.start, region.end + 1):
            yield self.test_module.addr.eq(i)
            yield Settle()
            mmio = yield self.test_module.result["mmio"]
            self.assertEqual(mmio, region.mmio)

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

        m.submodules.exception_report = self.exception_report = TestbenchIO(
            Adapter(i=self.gen.get(ExceptionRegisterLayouts).report)
        )

        self.gen.get(DependencyManager).add_dependency(ExceptionReportKey(), self.exception_report.adapter.iface)

        m.submodules.func_unit = func_unit = LSUDummy(self.gen, self.bus)

        m.submodules.select_mock = self.select = TestbenchIO(AdapterTrans(func_unit.select))
        m.submodules.insert_mock = self.insert = TestbenchIO(AdapterTrans(func_unit.insert))
        m.submodules.update_mock = self.update = TestbenchIO(AdapterTrans(func_unit.update))
        m.submodules.get_result_mock = self.get_result = TestbenchIO(AdapterTrans(func_unit.get_result))
        m.submodules.precommit_mock = self.precommit = TestbenchIO(AdapterTrans(func_unit.precommit))
        self.io_in = WishboneInterfaceWrapper(self.bus.wbMaster)
        m.submodules.bus = self.bus
        return m


class TestPMAIndirect(CoreblocksTestCaseWithSimulator):
    def get_instr(self, addr):
        return {
            "rp_s1": 0,
            "rp_s2": 0,
            "rp_dst": 1,
            "rob_id": 1,
            "exec_fn": {"op_type": OpType.LOAD, "funct3": Funct3.B, "funct7": 0},
            "s1_val": 0,
            "s2_val": 1,
            "imm": addr,
        }

    def verify_region(self, region: PMARegion):
        for addr in range(region.start, region.end + 1):
            instr = self.get_instr(addr)
            yield from self.test_module.select.call()
            yield from self.test_module.insert.call(rs_data=instr, rs_entry_id=1)
            if region.mmio is True:
                wb = self.test_module.io_in.wb
                for i in range(100):  # 100 cycles is more than enough
                    wb_requested = (yield wb.stb) and (yield wb.cyc)
                    self.assertEqual(wb_requested, False)

                yield from self.test_module.precommit.call(rob_id=1, side_fx=1)

            yield from self.test_module.io_in.slave_wait()
            yield from self.test_module.io_in.slave_respond((addr << (addr % 4) * 8))
            yield Settle()
            v = yield from self.test_module.get_result.call()
            self.assertEqual(v["result"], addr)

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
            self.assertTrue(False)

        with self.run_simulation(self.test_module) as sim:
            sim.add_sync_process(self.process)
