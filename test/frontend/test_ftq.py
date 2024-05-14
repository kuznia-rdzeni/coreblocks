import pytest
from parameterized import parameterized_class
import random

from amaranth import Elaboratable, Module
from amaranth.sim import Passive
from amaranth import *
from amaranth.lib.data import View

from transactron.lib import Adapter
from transactron.utils import ModuleConnector
from transactron.testing import TestCaseWithSimulator, TestbenchIO, def_method_mock, SimpleTestCircuit
from transactron.utils.dependencies import DependencyContext

from coreblocks.frontend.fetch.fetch_target_queue import FetchTargetQueue
from coreblocks.frontend.branch_prediction.iface import BranchPredictionUnitInterface
from coreblocks.arch import *
from coreblocks.params import *
from coreblocks.params.configurations import test_core_config
from coreblocks.interface.keys import FetchResumeKey
from coreblocks.interface.layouts import BranchPredictionLayouts, FTQPtr


class MockBPU(Elaboratable, BranchPredictionUnitInterface):
    def __init__(self, gen_params: GenParams):
        layouts = gen_params.get(BranchPredictionLayouts)

        self.request_io = TestbenchIO(Adapter(i=layouts.bpu_request))
        self.read_target_pred_io = TestbenchIO(Adapter(o=layouts.bpu_read_target_pred))
        self.read_pred_details_io = TestbenchIO(Adapter(o=layouts.bpu_read_pred_details))
        self.update_io = TestbenchIO(Adapter())
        self.flush_io = TestbenchIO(Adapter())

        self.request = self.request_io.adapter.iface
        self.read_target_pred = self.read_target_pred_io.adapter.iface
        self.read_pred_details = self.read_pred_details_io.adapter.iface
        self.update = self.update_io.adapter.iface
        self.flush = self.flush_io.adapter.iface

    def elaborate(self, platform):
        m = Module()

        m.submodules.request_io = self.request_io
        m.submodules.read_target_pred_io = self.read_target_pred_io
        m.submodules.read_pred_details_io = self.read_pred_details_io
        m.submodules.update_io = self.update_io
        m.submodules.flush_io = self.flush_io

        return m


@parameterized_class(
    ("name", "fetch_block_log"),
    [
        ("block4B", 2),
    ],
)
class TestFTQ(TestCaseWithSimulator):
    fetch_block_log: int

    @pytest.fixture(autouse=True)
    def setup(self, fixture_initialize_testing_env):
        self.pc = 0x100
        self.gen_params = GenParams(
            test_core_config.replace(start_pc=self.pc, fetch_block_bytes_log=self.fetch_block_log)
        )

        self.bpu = MockBPU(self.gen_params)
        self.ftq = SimpleTestCircuit(FetchTargetQueue(self.gen_params, self.bpu))
        self.fetch_resume_mock = TestbenchIO(Adapter())
        DependencyContext.get().add_dependency(FetchResumeKey(), self.fetch_resume_mock.adapter.iface)

        self.m = ModuleConnector(self.bpu, self.ftq)

        random.seed(41)

    @def_method_mock(lambda self: self.bpu.request_io)
    def bpu_req_mock(self, pc, ftq_idx, global_branch_history, bpu_stage):
        pass

    @def_method_mock(lambda self: self.bpu.read_target_pred_io)
    def bpu_target_pred_mock(self):
        return {"ftq_idx": FTQPtr(gp=self.gen_params), "pc": 0, "bpu_stage": 0, "global_branch_history": 0}

    @def_method_mock(lambda self: self.bpu.read_pred_details_io)
    def bpu_pred_details_mock(self):
        pred = Signal(self.gen_params.get(BranchPredictionLayouts).block_prediction)
        return {"ftq_idx": FTQPtr(gp=self.gen_params), "bpu_stage": 0, "bpu_meta": 0, "block_prediction": pred}

    @def_method_mock(lambda self: self.bpu.update_io)
    def bpu_update_moc(self):
        pass

    @def_method_mock(lambda self: self.bpu.flush_io)
    def bpu_flush_mock(self):
        pass

    def cache_process(self):
        yield Passive()

        while True:
            yield

    def fetch_out_check(self):
        yield

    def run_sim(self):
        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.cache_process)
            sim.add_sync_process(self.fetch_out_check)

    def test(self):

        self.run_sim()
