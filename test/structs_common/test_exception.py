from amaranth import *
from coreblocks.params.layouts import ROBLayouts

from coreblocks.structs_common.exception import ExceptionCauseRegister
from coreblocks.params import GenParams
from coreblocks.params.isa import ExceptionCause
from coreblocks.params.configurations import test_core_config
from transactron.lib import Adapter
from transactron.utils import ModuleConnector

from ..common import *

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

        # check only for causes that can possibly collide and should be updated (if priorty is equal,
        # result shouldn't be updated - first happened)
        if new_arg["rob_id"] == old_arg["rob_id"]:
            return (
                new_arg["cause"] == ExceptionCause.BREAKPOINT
                or (
                    (
                        new_arg["cause"] == ExceptionCause.INSTRUCTION_ACCESS_FAULT
                        or new_arg["cause"] == ExceptionCause.INSTRUCTION_PAGE_FAULT
                    )
                    and old_arg["cause"] != ExceptionCause.BREAKPOINT
                )
                or (
                    (
                        old_arg["cause"] == ExceptionCause.STORE_ACCESS_FAULT
                        or old_arg["cause"] == ExceptionCause.STORE_PAGE_FAULT
                    )
                    and new_arg["cause"] == ExceptionCause.STORE_ADDRESS_MISALIGNED
                )
                or (
                    (
                        old_arg["cause"] == ExceptionCause.LOAD_ACCESS_FAULT
                        or old_arg["cause"] == ExceptionCause.LOAD_PAGE_FAULT
                    )
                    and new_arg["cause"] == ExceptionCause.LOAD_ADDRESS_MISALIGNED
                )
            )

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
                report_pc = random.randrange(2**self.gen_params.isa.xlen)
                report_arg = {"cause": cause, "rob_id": report_rob, "pc": report_pc}

                yield from self.dut.report.call(report_arg)
                yield  # one cycle fifo delay

                new_state = yield from self.dut.get.call()

                if self.should_update(report_arg, saved_entry, self.rob_id):
                    self.assertDictEqual(new_state, report_arg)
                    saved_entry = report_arg
                elif saved_entry is not None:
                    self.assertDictEqual(new_state, saved_entry)

        @def_method_mock(lambda: self.rob_idx_mock)
        def process_rob_idx_mock():
            return {"start": self.rob_id, "end": 0}

        with self.run_simulation(m) as sim:
            sim.add_sync_process(process_test)
            sim.add_sync_process(process_rob_idx_mock)
