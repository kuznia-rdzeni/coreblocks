import random
from collections import deque
import pytest
import itertools

from transactron.testing import TestCaseWithSimulator, SimpleTestCircuit, TestbenchContext

from coreblocks.func_blocks.fu.common.rs import RS, RSBase
from coreblocks.func_blocks.fu.common.fifo_rs import FifoRS
from coreblocks.params import *
from coreblocks.params.configurations import test_core_config
from coreblocks.arch import OpType
from transactron.testing.functions import data_const_to_dict


def create_check_list(rs_entries_bits: int, insert_list: list[dict]) -> list[dict]:
    check_list = [{"rs_data": None, "rec_reserved": 0, "rec_full": 0} for _ in range(2**rs_entries_bits)]

    for params in insert_list:
        entry_id = params["rs_entry_id"]
        check_list[entry_id]["rs_data"] = params["rs_data"]
        check_list[entry_id]["rec_full"] = 1
        check_list[entry_id]["rec_reserved"] = 1

    return check_list


def create_data_list(gen_params: GenParams, count: int, optypes: int = 1):
    data_list = [
        {
            "rp_s1": random.randrange(1, 2**gen_params.phys_regs_bits) * random.randrange(2),
            "rp_s2": random.randrange(1, 2**gen_params.phys_regs_bits) * random.randrange(2),
            "rp_dst": random.randrange(2**gen_params.phys_regs_bits),
            "rob_id": k,
            "exec_fn": {
                "op_type": OpType(random.randint(1, optypes)),
                "funct3": 2,
                "funct7": 4,
            },
            "s1_val": k,
            "s2_val": k,
            "imm": k,
            "pc": k,
            "tag": 0,
        }
        for k in range(count)
    ]
    return data_list


@pytest.mark.parametrize(
    "rs_type",
    [
        RS,
        FifoRS,
    ],
)
@pytest.mark.parametrize("ready_lists", [1, 2])
class TestRS(TestCaseWithSimulator):
    def test_rs(self, rs_type: type[RSBase], ready_lists: int):
        random.seed(42)
        optypes_per_list = 2
        num_optypes = optypes_per_list * ready_lists
        optypes = [OpType(k + 1) for k in range(num_optypes)]
        self.optype_groups = list(zip(*(iter(optypes),) * optypes_per_list))
        self.gen_params = GenParams(test_core_config)
        self.rs_entries_bits = self.gen_params.max_rs_entries_bits
        self.m = SimpleTestCircuit(rs_type(self.gen_params, 2**self.rs_entries_bits, 0, self.optype_groups))
        self.data_list = create_data_list(self.gen_params, 10 * 2**self.rs_entries_bits, num_optypes)
        self.select_queue: deque[int] = deque()
        self.regs_to_update: set[int] = set()
        self.rs_entries: dict[int, int] = {}
        self.finished = False

        with self.run_simulation(self.m) as sim:
            sim.add_testbench(self.select_process)
            sim.add_testbench(self.insert_process)
            sim.add_testbench(self.update_process)
            sim.add_testbench(self.take_process)

    async def select_process(self, sim: TestbenchContext):
        for k in range(len(self.data_list)):
            await self.random_wait_geom(sim, 0.5)
            rs_entry_id = (await self.m.select.call(sim)).rs_entry_id
            self.select_queue.appendleft(rs_entry_id)
            self.rs_entries[rs_entry_id] = k

    async def insert_process(self, sim: TestbenchContext):
        for data in self.data_list:
            await self.random_wait_geom(sim, 0.7)
            await sim.delay(1e-9)  # so that select_process can insert into the queue
            while not self.select_queue:
                await sim.tick()
                await sim.delay(1e-9)
            rs_entry_id = self.select_queue.pop()
            await self.m.insert.call(sim, rs_entry_id=rs_entry_id, rs_data=data)
            if data["rp_s1"]:
                self.regs_to_update.add(data["rp_s1"])
            if data["rp_s2"]:
                self.regs_to_update.add(data["rp_s2"])

    async def update_process(self, sim: TestbenchContext):
        while not self.finished:
            await self.random_wait_geom(sim, 0.5)
            await sim.delay(1e-9)  # so that insert_process can insert into the set
            if not self.regs_to_update:
                await sim.tick()
                continue
            reg_id = random.choice(list(self.regs_to_update))
            self.regs_to_update.discard(reg_id)
            reg_val = random.randrange(1000)
            for rs_entry_id, k in self.rs_entries.items():
                if self.data_list[k]["rp_s1"] == reg_id:
                    self.data_list[k]["rp_s1"] = 0
                    self.data_list[k]["s1_val"] = reg_val
                if self.data_list[k]["rp_s2"] == reg_id:
                    self.data_list[k]["rp_s2"] = 0
                    self.data_list[k]["s2_val"] = reg_val
            await self.m.update.call(sim, reg_id=reg_id, reg_val=reg_val)

    async def take_process(self, sim: TestbenchContext):
        taken: set[int] = set()
        for i in range(len(self.optype_groups)):
            self.m.get_ready_list[i].call_init(sim)
        for _ in range(len(self.data_list)):
            while not any(self.m.get_ready_list[i].get_done(sim) for i in range(len(self.optype_groups))):
                await sim.tick()
            await self.random_wait_geom(sim, 0.5)

            def get_possible_ids():
                ready_lists = []
                for i in range(len(self.optype_groups)):
                    ready_list = self.m.get_ready_list[i].get_call_result(sim)
                    ready_lists.append(ready_list.ready_list if ready_list is not None else 0)
                return [
                    [i for i in range(2**self.rs_entries_bits) if ready_list & (1 << i)] for ready_list in ready_lists
                ]

            while not list(itertools.chain(*(possible_ids := get_possible_ids()))):
                await sim.tick()
            optype_group = random.choice(list(k for k, idxs in enumerate(possible_ids) if idxs))
            rs_idx = random.choice(possible_ids[optype_group])
            rs_entry_id = sim.get(self.m._dut.order[rs_idx])
            k = self.rs_entries[rs_entry_id]
            taken.add(k)
            test_data = dict(self.data_list[k])
            del test_data["rp_s1"]
            del test_data["rp_s2"]
            data = await self.m.take.call(sim, rs_entry_id=rs_idx)
            assert data_const_to_dict(data) == test_data
            assert data.exec_fn.op_type in self.optype_groups[optype_group]
        assert taken == set(range(len(self.data_list)))
        self.finished = True
