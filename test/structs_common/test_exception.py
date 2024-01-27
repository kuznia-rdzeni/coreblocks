from amaranth import *
from coreblocks.params.layouts import ROBLayouts

from coreblocks.structs_common.exception import ExceptionCauseRegister
from coreblocks.params import GenParams
from coreblocks.params.isa import ExceptionCause
from coreblocks.params.configurations import test_core_config
from transactron.lib import Adapter
from transactron.utils import ModuleConnector

from transactron.testing import *

import random


class TestExceptionCauseRegister(TestCaseWithSimulator):
    rob_max = 7

    def should_update(self, new_arg, old_arg, rob_start) -> bool:
        if old_arg is None:
            return True

        if ((new_arg["rob_id"] - rob_start) % (self.rob_max + 1)) < (
            (old_arg["rob_id"] - rob_start) % (self.rob_max + 1)
        ):
            return True

        return False

    def test_randomized(self):
        self.gen_params = GenParams(test_core_config)
        random.seed(2)

        self.cycles = 256

        self.rob_idx_mock = TestbenchIO(Adapter(o=self.gen_params.get(ROBLayouts).get_indices))
        self.dut = SimpleTestCircuit(ExceptionCauseRegister(self.gen_params, self.rob_idx_mock.adapter.iface))
        m = ModuleConnector(self.dut, rob_idx_mock=self.rob_idx_mock)

        self.rob_id = 0

        def process_test():
            saved_entry = None

            for _ in range(self.cycles):
                self.rob_id = random.randint(0, self.rob_max)

                cause = random.choice(list(ExceptionCause))
                report_rob = random.randint(0, self.rob_max)
                # only one exception per rob_id
                while saved_entry and report_rob == saved_entry["rob_id"]:
                    report_rob = random.randint(0, self.rob_max)
                report_pc = random.randrange(2**self.gen_params.isa.xlen)
                report_arg = {"cause": cause, "rob_id": report_rob, "pc": report_pc}

                expected = report_arg if self.should_update(report_arg, saved_entry, self.rob_id) else saved_entry
                yield from self.dut.report.call(report_arg)
                yield  # additional FIFO delay

                new_state = yield from self.dut.get.call()

                self.assertDictEqual(new_state, expected | {"valid": 1})  # type: ignore

                saved_entry = new_state

        @def_method_mock(lambda: self.rob_idx_mock)
        def process_rob_idx_mock():
            return {"start": self.rob_id, "end": 0}

        with self.run_simulation(m) as sim:
            sim.add_sync_process(process_test)
