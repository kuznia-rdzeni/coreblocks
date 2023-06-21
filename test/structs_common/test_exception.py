from amaranth import *
from coreblocks.params.layouts import ROBLayouts

from coreblocks.structs_common.exception import ExceptionCauseRegister, Cause
from coreblocks.params import GenParams
from coreblocks.params.configurations import test_core_config
from coreblocks.transactions.lib import Adapter

from ..common import *

import random


class ExceptionCauseTestCircuit(Elaboratable):
    def __init__(self, gen_params):
        self.gen_params = gen_params

    def elaborate(self, platform):
        m = Module()

        m.submodules.rob_idx = self.rob_idx = TestbenchIO(Adapter(o=self.gen_params.get(ROBLayouts).get_indices))

        m.submodules.dut = self.dut = ExceptionCauseRegister(
            self.gen_params, rob_get_indices=self.rob_idx.adapter.iface
        )

        m.submodules.report = self.report = TestbenchIO(AdapterTrans(self.dut.report))
        m.submodules.get = self.get = TestbenchIO(AdapterTrans(self.dut.get))

        return m


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
                new_arg["cause"] == Cause.BREAKPOINT
                or (
                    (
                        new_arg["cause"] == Cause.INSTRUCTION_ACCESS_FAULT
                        or new_arg["cause"] == Cause.INSTRUCTION_PAGE_FAULT
                    )
                    and old_arg["cause"] != Cause.BREAKPOINT
                )
                or (
                    (old_arg["cause"] == Cause.STORE_ACCESS_FAULT or old_arg["cause"] == Cause.STORE_PAGE_FAULT)
                    and new_arg["cause"] == Cause.STORE_ADDRESS_MISALIGNED
                )
                or (
                    (old_arg["cause"] == Cause.LOAD_ACCESS_FAULT or old_arg["cause"] == Cause.LOAD_PAGE_FAULT)
                    and new_arg["cause"] == Cause.LOAD_ADDRESS_MISALIGNED
                )
            )

        return False

    def process_test(self):
        saved_entry = None

        yield from self.dut.rob_idx.enable()
        for _ in range(self.cycles):
            rob_rand = random.randint(0, self.rob_max)
            yield from self.dut.rob_idx.set_inputs({"start": rob_rand, "end": 0})
            yield Settle()

            cause = random.choice(list(Cause))
            report_rob = random.randint(0, self.rob_max)
            report_arg = {"cause": cause, "rob_id": report_rob}

            yield from self.dut.report.call(report_arg)

            new_state = yield from self.dut.get.call()

            if self.should_update(report_arg, saved_entry, rob_rand):
                self.assertDictEqual(new_state, report_arg)
                saved_entry = report_arg
            elif saved_entry is not None:
                self.assertDictEqual(new_state, saved_entry)

    def test_randomized(self):
        self.gp = GenParams(test_core_config)
        random.seed(2)

        self.cycles = 256

        self.dut = ExceptionCauseTestCircuit(self.gp)

        with self.run_simulation(self.dut) as sim:
            sim.add_sync_process(self.process_test)
