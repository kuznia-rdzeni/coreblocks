from typing import Optional, cast
from amaranth import *
from amaranth.lib.data import StructLayout

from collections import deque
from enum import Enum
from inspect import isclass
import random

from coreblocks.params import GenParams
from coreblocks.params.configurations import test_core_config
from coreblocks.func_blocks.fu.common.rs_func_block import RSBlockComponent
from transactron import *
from coreblocks.scheduler.wakeup_select import *

from transactron.testing import RecordIntDict, SimpleTestCircuit, TestCaseWithSimulator, TestbenchContext
from transactron.testing.functions import data_const_to_dict


class TestWakeupSelect(TestCaseWithSimulator):
    def setup_method(self):
        self.gen_params = GenParams(
            test_core_config.replace(
                func_units_config=tuple(RSBlockComponent([], rs_entries=16, rs_number=k) for k in range(2))
            )
        )
        self.m = SimpleTestCircuit(
            WakeupSelect(gen_params=self.gen_params, rs_entries_bits=self.gen_params.max_rs_entries_bits)
        )
        self.cycles = 50
        self.taken = deque()

        random.seed(42)

    def random_entry(self, layout: StructLayout) -> RecordIntDict:
        result = {}
        for key, width_or_layout in layout.members.items():
            if isinstance(width_or_layout, int):
                result[key] = random.randrange(width_or_layout)
            elif isclass(width_or_layout) and issubclass(width_or_layout, Enum):
                result[key] = random.choice(list(width_or_layout))
            elif isinstance(width_or_layout, StructLayout):
                result[key] = self.random_entry(width_or_layout)
        return result

    def maybe_insert(self, rs: list[Optional[RecordIntDict]]):
        empty_entries = sum(1 for entry in rs if entry is None)
        if empty_entries > 0 and random.random() < 0.5:
            empty_idx = random.randrange(empty_entries)
            for i, entry in enumerate(rs):
                if entry is None:
                    if empty_idx == 0:
                        rs[i] = self.random_entry(self.m._dut.take_row.layout_out)
                        return 1
                    empty_idx -= 1
        return 0

    async def process(self, sim: TestbenchContext):
        inserted_count = 0
        issued_count = 0
        rs: list[Optional[RecordIntDict]] = [None for _ in range(self.gen_params.max_rs_entries)]

        self.m.take_row.enable(sim)
        self.m.issue.enable(sim)
        for _ in range(self.cycles):
            inserted_count += self.maybe_insert(rs)
            ready = Const.cast(Cat(entry is not None for entry in rs))

            self.m.get_ready.call_init(sim, ready_list=ready)
            self.m.get_ready.set_enable(sim, any(entry is not None for entry in rs))

            take_position = self.m.take_row.get_call_result(sim)
            if take_position is not None:
                take_position = cast(int, take_position["rs_entry_id"])
                entry = rs[take_position]
                assert entry is not None

                self.taken.append(entry)
                self.m.take_row.call_init(sim, entry)
                rs[take_position] = None

                issued = self.m.issue.get_call_result(sim)
                if issued is not None:
                    assert data_const_to_dict(issued) == self.taken.popleft()
                    issued_count += 1
            await sim.tick()
        assert inserted_count != 0
        assert inserted_count == issued_count

    def test(self):
        with self.run_simulation(self.m) as sim:
            sim.add_testbench(self.process)
