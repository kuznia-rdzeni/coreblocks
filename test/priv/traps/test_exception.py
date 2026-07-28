from amaranth import *
from coreblocks.interface.keys import ActiveTagsKey
from coreblocks.interface.layouts import RATLayouts

from coreblocks.priv.traps.exception import ExceptionInformationRegister
from coreblocks.params import GenParams
from coreblocks.arch import ExceptionCause
from coreblocks.params import configurations
from transactron.lib import Adapter
from transactron.utils import DependencyContext, ModuleConnector

from transactron.testing import *

import random


class TestExceptionInformationRegister(TestCaseWithSimulator):
    rob_max = 7

    def should_update(self, new_arg, old_arg) -> bool:
        if not ((self.active_tags >> new_arg["tag"]) & 1):
            return False

        if old_arg is None:
            return True

        if ((new_arg["rob_id"] - self.rob_id) % (self.rob_max + 1)) < (
            (old_arg["rob_id"] - self.rob_id) % (self.rob_max + 1)
        ):
            return True

        return False

    def test_randomized(self):
        self.gen_params = GenParams(configurations.test)
        random.seed(2)

        cycles = 256
        tag_count = 4

        self.tags_active = TestbenchIO(Adapter(o=self.gen_params.get(RATLayouts).get_active_tags_out))
        DependencyContext.get().add_dependency(ActiveTagsKey(), self.tags_active.adapter.iface)

        self.dut = SimpleTestCircuit(
            ExceptionInformationRegister(self.gen_params),
        )
        m = ModuleConnector(self.dut, self.tags_active)

        self.rob_id = 0
        self.active_tags = 0

        async def process_test(sim: TestbenchContext):
            saved_entry = None

            for _ in range(cycles):
                self.rob_id = random.randint(0, self.rob_max)

                cause = random.choice(list(ExceptionCause))
                report_rob = random.randint(0, self.rob_max)
                # only one exception per rob_id
                while saved_entry and report_rob == saved_entry["rob_id"]:
                    report_rob = random.randint(0, self.rob_max)
                report_pc = random.randrange(2**self.gen_params.isa.xlen)
                report_mtval = random.randrange(2**self.gen_params.isa.xlen)
                report_tag = random.randrange(tag_count)
                report_arg = {
                    "cause": cause,
                    "rob_id": report_rob,
                    "pc": report_pc,
                    "mtval": report_mtval,
                    "tag": report_tag,
                }

                expected = report_arg if self.should_update(report_arg, saved_entry) else saved_entry
                await self.dut.report.call(sim, report_arg)

                new_state = data_const_to_dict(await self.dut.get.call(sim))

                if expected is not None:
                    assert new_state == {"data": expected, "valid": 1}
                    saved_entry = new_state["data"]
                else:
                    assert not new_state["valid"]

                if random.random() < 0.4:
                    self.active_tags = random.randrange(2**tag_count)
                    await sim.tick()
                    new_state = data_const_to_dict(await self.dut.get.call(sim))
                    if saved_entry and (self.active_tags >> saved_entry["tag"]) & 1:
                        assert new_state == {"data": saved_entry, "valid": 1}
                        saved_entry = new_state["data"]
                    else:
                        assert not new_state["valid"]
                        saved_entry = None

        @def_method_mock(lambda: self.dut.rob_get_indices)
        def process_rob_idx_mock():
            return {"start": self.rob_id, "end": 0}

        @def_method_mock(lambda: self.tags_active)  # type: ignore
        def process_tags_active():
            return {
                "active_tags": [
                    (self.active_tags >> i) & 1 for i in range(self.tags_active.adapter.iface.layout_out.size)
                ]
            }

        with self.run_simulation(m) as sim:
            sim.add_testbench(process_test)
