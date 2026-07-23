from collections import deque
import random
from amaranth.utils import exact_log2
import pytest
from amaranth import *
from transactron.utils import DependencyContext, ModuleConnector

from coreblocks.frontend.frontend import CoreFrontend
from coreblocks.interface.keys import (
    ActiveTagsKey,
    CSRInstancesKey,
    CoreStateKey,
    FTQCommitKey,
    UnsafeInstructionResolvedKey,
)
from coreblocks.interface.layouts import RATLayouts, RetirementLayouts
from coreblocks.params import configurations
from coreblocks.params.genparams import GenParams
from coreblocks.priv.csr.csr_instances import CSRInstances
from coreblocks.priv.traps.exception import ExceptionInformationRegister

from transactron.lib import Adapter, AdapterTrans
from transactron.testing import *
from transactron.core import *

from test.peripherals.bus_mock import BusMockParameters, MockMasterAdapter


class TestFrontend(TestCaseWithSimulator):
    @pytest.fixture(autouse=True)
    def setup(self):
        self.gen_params = GenParams(configurations.test)

        self.dm = DependencyContext.get()

        self.csr_instances = CSRInstances(self.gen_params)
        self.dm.add_dependency(CSRInstancesKey(), self.csr_instances)

        self.tags_active = TestbenchIO(Adapter(o=self.gen_params.get(RATLayouts).get_active_tags_out))
        DependencyContext.get().add_dependency(ActiveTagsKey(), self.tags_active.adapter.iface)

        self.bus = MockMasterAdapter(
            BusMockParameters(data_width=self.gen_params.isa.xlen, addr_width=self.gen_params.isa.xlen)
        )
        self.eir = SimpleTestCircuit(ExceptionInformationRegister(self.gen_params))

        self.frontend = SimpleTestCircuit(CoreFrontend(gen_params=self.gen_params, instr_bus=self.bus))

        self.resolve = TestbenchIO(AdapterTrans.create(self.dm.get_dependency(UnsafeInstructionResolvedKey())))

        ftq_commit = self.dm.get_dependency(FTQCommitKey())
        self.ftq_commit = TestbenchIO(AdapterTrans.create(ftq_commit))

        self.core_state = TestbenchIO(Adapter(o=self.gen_params.get(RetirementLayouts).core_state))
        self.dm.add_dependency(CoreStateKey(), self.core_state.adapter.iface)

        self.m = ModuleConnector(
            self.frontend,
            self.bus,
            self.eir,
            self.csr_instances,
            self.tags_active,
            self.resolve,
            self.ftq_commit,
            self.core_state,
        )

        self.stall_resume_pc = None
        self.in_stall = False
        self.flushing = False

        self.unsafe_resume = None

        self.pending_exception = None
        self.stall_exception = None
        self.ftq_commit_queue = deque()
        self.ftq_commit_ignored = deque()

        random.seed(42)

    async def consume_process(self, sim):
        next_pc = 0x0
        cnt = 0
        while True:
            instrs = await self.frontend.consume_instr.call_try(sim)

            if instrs is None:
                await self.random_wait(sim, 8)
                continue

            for idx, instr in enumerate(instrs["data"]):
                if idx >= instrs["count"]:
                    continue

                if self.in_stall:
                    assert instr["pc"] == self.stall_resume_pc
                    next_pc = instr["pc"]
                    self.in_stall = False
                    self.stall_exception = False

                if instr["pc"] % 0x100 == 0x0:
                    self.in_stall = True
                    self.unsafe_resume = {"pc": instr["pc"] + 0x4, "ftq_ptr": instr["ftq_ptr"]}
                    assert idx == instrs["count"] - 1

                assert instr["pc"] == next_pc
                next_pc = instr["pc"] + 0x4

            cnt += instrs["count"]
            if cnt > 200:
                break

            if random.random() < 1 / 20 and self.pending_exception is None:
                self.pending_exception = random.choice(
                    [
                        {"pc": instrs["data"][i]["pc"], "ftq_ptr": instrs["data"][i]["ftq_ptr"]}
                        for i in range(instrs["count"])
                    ]
                )

                await self.random_wait(sim, 8)
                await self.eir.report.call(sim)
                self.stall_exception = True

            if not self.stall_exception:
                for idx, instr in enumerate(instrs["data"]):
                    if idx >= instrs["count"]:
                        continue
                    self.ftq_commit_queue.appendleft(instr["ftq_ptr"])

            await self.random_wait_geom(sim, 0.7)

    async def exception_process(self, sim):
        while True:
            await self.random_wait_geom(sim, 0.5)
            if self.stall_exception and self.pending_exception:
                await sim.tick()  # wait tick for a frontend flush to trigger
                self.in_stall = True
                self.stall_resume_pc = (random.randrange(0x400) // 4) * 4
                self.flushing = True
                await self.random_wait(sim, 4)
                await CallTrigger(sim).call(self.eir.clear).call(
                    self.frontend.redirect, pc=self.stall_resume_pc, ftq_ptr=self.pending_exception["ftq_ptr"]
                )
                self.pending_exception = None
                self.flushing = False

    async def instr_verify_process(self, sim):
        while True:
            await self.random_wait(sim, 30)
            if self.unsafe_resume is not None:
                self.in_stall = True
                await self.resolve.call(sim, pc=self.unsafe_resume["pc"], ftq_ptr=self.unsafe_resume["ftq_ptr"])
                if not self.stall_exception:
                    self.stall_resume_pc = self.unsafe_resume["pc"]
                self.unsafe_resume = None

    async def bus_process(self, sim: TestbenchContext):
        while True:
            req = await self.bus.request_read_mock.call(sim)

            addr = req.addr << exact_log2(self.gen_params.icache_params.word_width_bytes)

            await self.random_wait_geom(sim, 0.5)

            def gen_instr(addr):
                if addr % 0x100 == 0:
                    return 0x00000073 | (addr << 7)  # unsafe instr
                return 0x00000013 | (addr << 7)  # regular instr

            data = 0
            for i in range(0, self.bus.params.data_width // 8, 4):
                data |= gen_instr(addr + i) << (8 * i)

            await self.bus.get_read_response_mock.call(sim, data=data, err=0)

    @def_method_mock(lambda self: self.eir.rob_get_indices)
    def process_rob_idx_mock(self):
        return {"start": 0, "end": 0}

    @def_method_mock(lambda self: self.tags_active)  # type: ignore
    def process_tags_active(self):
        return {"active_tags": [1 for _ in range(self.tags_active.adapter.iface.layout_out.size)]}

    @def_method_mock(lambda self: self.core_state)
    def core_state_mock(self):
        return {"flushing": self.flushing}

    async def eir_get_proxy(self, sim):
        self.eir.get.call_init(sim)
        while True:
            data = self.eir.get.get_outputs(sim)
            await self.frontend.get_exception_information.call(sim, data=data["data"], valid=data["valid"])

    async def ftq_commit_process(self, sim):
        while True:
            await self.random_wait(sim, 5)

            if not self.ftq_commit_queue:
                continue

            await self.ftq_commit.call(sim, ftq_ptr=self.ftq_commit_queue.pop())

    def test_frontend(self):
        with self.run_simulation(self.m, max_cycles=1500) as sim:
            sim.add_testbench(self.consume_process)
            sim.add_testbench(self.exception_process, background=True)
            sim.add_testbench(self.instr_verify_process, background=True)
            sim.add_testbench(self.bus_process, background=True)
            sim.add_testbench(self.eir_get_proxy, background=True)
            sim.add_testbench(self.ftq_commit_process, background=True)
