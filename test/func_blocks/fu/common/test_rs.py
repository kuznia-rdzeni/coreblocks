import random
from collections import deque
from parameterized import parameterized_class

from amaranth.sim import Settle

from transactron.testing import TestCaseWithSimulator, get_outputs, SimpleTestCircuit

from coreblocks.func_blocks.fu.common.rs import RS, RSBase
from coreblocks.func_blocks.fu.common.fifo_rs import FifoRS
from coreblocks.params import *
from coreblocks.params.configurations import test_core_config
from coreblocks.arch import OpType


def create_check_list(rs_entries_bits: int, insert_list: list[dict]) -> list[dict]:
    check_list = [{"rs_data": None, "rec_reserved": 0, "rec_full": 0} for _ in range(2**rs_entries_bits)]

    for params in insert_list:
        entry_id = params["rs_entry_id"]
        check_list[entry_id]["rs_data"] = params["rs_data"]
        check_list[entry_id]["rec_full"] = 1
        check_list[entry_id]["rec_reserved"] = 1

    return check_list


def create_data_list(gen_params: GenParams, count: int):
    data_list = [
        {
            "rp_s1": random.randrange(1, 2**gen_params.phys_regs_bits) * random.randrange(2),
            "rp_s2": random.randrange(1, 2**gen_params.phys_regs_bits) * random.randrange(2),
            "rp_dst": random.randrange(2**gen_params.phys_regs_bits),
            "rob_id": k,
            "exec_fn": {
                "op_type": 1,
                "funct3": 2,
                "funct7": 3,
            },
            "s1_val": k,
            "s2_val": k,
            "imm": k,
            "pc": k,
        }
        for k in range(count)
    ]
    return data_list


@parameterized_class(
    ("name", "rs_elaboratable"),
    [
        (
            "RS",
            RS,
        ),
        (
            "FifoRS",
            FifoRS,
        ),
    ],
)
class TestRS(TestCaseWithSimulator):
    rs_elaboratable: type[RSBase]

    def test_rs(self):
        random.seed(42)
        self.gen_params = GenParams(test_core_config)
        self.rs_entries_bits = self.gen_params.max_rs_entries_bits
        self.m = SimpleTestCircuit(self.rs_elaboratable(self.gen_params, 2**self.rs_entries_bits, 0, None))
        self.data_list = create_data_list(self.gen_params, 10 * 2**self.rs_entries_bits)
        self.select_queue: deque[int] = deque()
        self.regs_to_update: set[int] = set()
        self.rs_entries: dict[int, int] = {}
        self.finished = False

        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.select_process)
            sim.add_sync_process(self.insert_process)
            sim.add_sync_process(self.update_process)
            sim.add_sync_process(self.take_process)

    def select_process(self):
        for k in range(len(self.data_list)):
            rs_entry_id = (yield from self.m.select.call())["rs_entry_id"]
            self.select_queue.appendleft(rs_entry_id)
            self.rs_entries[rs_entry_id] = k

    def insert_process(self):
        for data in self.data_list:
            yield Settle()  # so that select_process can insert into the queue
            while not self.select_queue:
                yield
                yield Settle()
            rs_entry_id = self.select_queue.pop()
            yield from self.m.insert.call({"rs_entry_id": rs_entry_id, "rs_data": data})
            if data["rp_s1"]:
                self.regs_to_update.add(data["rp_s1"])
            if data["rp_s2"]:
                self.regs_to_update.add(data["rp_s2"])

    def update_process(self):
        while not self.finished:
            yield Settle()  # so that insert_process can insert into the set
            if not self.regs_to_update:
                yield
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
            yield from self.m.update.call(reg_id=reg_id, reg_val=reg_val)

    def take_process(self):
        taken: set[int] = set()
        yield from self.m.get_ready_list[0].call_init()
        yield Settle()
        for k in range(len(self.data_list)):
            yield Settle()
            while not (yield from self.m.get_ready_list[0].done()):
                yield
            ready_list = (yield from self.m.get_ready_list[0].call_result())["ready_list"]
            possible_ids = [i for i in range(2**self.rs_entries_bits) if ready_list & (1 << i)]
            if not possible_ids:
                yield
                continue
            rs_entry_id = random.choice(possible_ids)
            k = self.rs_entries[rs_entry_id]
            taken.add(k)
            test_data = dict(self.data_list[k])
            del test_data["rp_s1"]
            del test_data["rp_s2"]
            data = yield from self.m.take.call(rs_entry_id=rs_entry_id)
            assert data == test_data
        assert taken == set(range(len(self.data_list)))
        self.finished = True


class TestRSMethodInsert(TestCaseWithSimulator):
    def test_insert(self):
        self.gen_params = GenParams(test_core_config)
        self.rs_entries_bits = self.gen_params.max_rs_entries_bits
        self.m = SimpleTestCircuit(RS(self.gen_params, 2**self.rs_entries_bits, 0, None))
        self.insert_list = [
            {
                "rs_entry_id": id,
                "rs_data": {
                    "rp_s1": id * 2,
                    "rp_s2": id * 2 + 1,
                    "rp_dst": id * 2,
                    "rob_id": id,
                    "exec_fn": {
                        "op_type": 1,
                        "funct3": 2,
                        "funct7": 3,
                    },
                    "s1_val": id,
                    "s2_val": id,
                    "imm": id,
                    "pc": id,
                },
            }
            for id in range(2**self.rs_entries_bits)
        ]
        self.check_list = create_check_list(self.rs_entries_bits, self.insert_list)

        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.simulation_process)

    def simulation_process(self):
        # After each insert, entry should be marked as full
        for index, record in enumerate(self.insert_list):
            assert (yield self.m._dut.data[index].rec_full) == 0
            yield from self.m.insert.call(record)
            yield Settle()
            assert (yield self.m._dut.data[index].rec_full) == 1
        yield Settle()

        # Check data integrity
        for expected, record in zip(self.check_list, self.m._dut.data):
            assert expected == (yield from get_outputs(record))


class TestRSMethodSelect(TestCaseWithSimulator):
    def test_select(self):
        self.gen_params = GenParams(test_core_config)
        self.rs_entries_bits = self.gen_params.max_rs_entries_bits
        self.m = SimpleTestCircuit(RS(self.gen_params, 2**self.rs_entries_bits, 0, None))
        self.insert_list = [
            {
                "rs_entry_id": id,
                "rs_data": {
                    "rp_s1": id * 2,
                    "rp_s2": id * 2,
                    "rp_dst": id * 2,
                    "rob_id": id,
                    "exec_fn": {
                        "op_type": 1,
                        "funct3": 2,
                        "funct7": 3,
                    },
                    "s1_val": id,
                    "s2_val": id,
                    "imm": id,
                    "pc": id,
                },
            }
            for id in range(2**self.rs_entries_bits - 1)
        ]
        self.check_list = create_check_list(self.rs_entries_bits, self.insert_list)

        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.simulation_process)

    def simulation_process(self):
        # In the beginning the select method should be ready and id should be selectable
        for index, record in enumerate(self.insert_list):
            assert (yield self.m._dut.select.ready) == 1
            assert (yield from self.m.select.call())["rs_entry_id"] == index
            yield Settle()
            assert (yield self.m._dut.data[index].rec_reserved) == 1
            yield from self.m.insert.call(record)
        yield Settle()

        # Check if RS state is as expected
        for expected, record in zip(self.check_list, self.m._dut.data):
            assert (yield record.rec_full) == expected["rec_full"]
            assert (yield record.rec_reserved) == expected["rec_reserved"]

        # Reserve the last entry, then select ready should be false
        assert (yield self.m._dut.select.ready) == 1
        assert (yield from self.m.select.call())["rs_entry_id"] == 3
        yield Settle()
        assert (yield self.m._dut.select.ready) == 0

        # After take, select ready should be true, with 0 index returned
        yield from self.m.take.call(rs_entry_id=0)
        yield Settle()
        assert (yield self.m._dut.select.ready) == 1
        assert (yield from self.m.select.call())["rs_entry_id"] == 0

        # After reservation, select is false again
        yield Settle()
        assert (yield self.m._dut.select.ready) == 0


class TestRSMethodUpdate(TestCaseWithSimulator):
    def test_update(self):
        self.gen_params = GenParams(test_core_config)
        self.rs_entries_bits = self.gen_params.max_rs_entries_bits
        self.m = SimpleTestCircuit(RS(self.gen_params, 2**self.rs_entries_bits, 0, None))
        self.insert_list = [
            {
                "rs_entry_id": id,
                "rs_data": {
                    "rp_s1": id * 2,
                    "rp_s2": id * 2 + 1,
                    "rp_dst": id * 2,
                    "rob_id": id,
                    "exec_fn": {
                        "op_type": 1,
                        "funct3": 2,
                        "funct7": 3,
                    },
                    "s1_val": id,
                    "s2_val": id,
                    "imm": id,
                    "pc": id,
                },
            }
            for id in range(2**self.rs_entries_bits)
        ]
        self.check_list = create_check_list(self.rs_entries_bits, self.insert_list)

        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.simulation_process)

    def simulation_process(self):
        # Insert all reacords
        for record in self.insert_list:
            yield from self.m.insert.call(record)
        yield Settle()

        # Check data integrity
        for expected, record in zip(self.check_list, self.m._dut.data):
            assert expected == (yield from get_outputs(record))

        # Update second entry first SP, instruction should be not ready
        value_sp1 = 1010
        assert (yield self.m._dut.data_ready[1]) == 0
        yield from self.m.update.call(reg_id=2, reg_val=value_sp1)
        yield Settle()
        assert (yield self.m._dut.data[1].rs_data.rp_s1) == 0
        assert (yield self.m._dut.data[1].rs_data.s1_val) == value_sp1
        assert (yield self.m._dut.data_ready[1]) == 0

        # Update second entry second SP, instruction should be ready
        value_sp2 = 2020
        yield from self.m.update.call(reg_id=3, reg_val=value_sp2)
        yield Settle()
        assert (yield self.m._dut.data[1].rs_data.rp_s2) == 0
        assert (yield self.m._dut.data[1].rs_data.s2_val) == value_sp2
        assert (yield self.m._dut.data_ready[1]) == 1

        # Insert new instruction to entries 0 and 1, check if update of multiple registers works
        reg_id = 4
        value_spx = 3030
        data = {
            "rp_s1": reg_id,
            "rp_s2": reg_id,
            "rp_dst": 1,
            "rob_id": 12,
            "exec_fn": {
                "op_type": 1,
                "funct3": 2,
                "funct7": 3,
            },
            "s1_val": 0,
            "s2_val": 0,
            "pc": 40,
        }

        for index in range(2):
            yield from self.m.insert.call(rs_entry_id=index, rs_data=data)
            yield Settle()
            assert (yield self.m._dut.data_ready[index]) == 0

        yield from self.m.update.call(reg_id=reg_id, reg_val=value_spx)
        yield Settle()
        for index in range(2):
            assert (yield self.m._dut.data[index].rs_data.rp_s1) == 0
            assert (yield self.m._dut.data[index].rs_data.rp_s2) == 0
            assert (yield self.m._dut.data[index].rs_data.s1_val) == value_spx
            assert (yield self.m._dut.data[index].rs_data.s2_val) == value_spx
            assert (yield self.m._dut.data_ready[index]) == 1


class TestRSMethodTake(TestCaseWithSimulator):
    def test_take(self):
        self.gen_params = GenParams(test_core_config)
        self.rs_entries_bits = self.gen_params.max_rs_entries_bits
        self.m = SimpleTestCircuit(RS(self.gen_params, 2**self.rs_entries_bits, 0, None))
        self.insert_list = [
            {
                "rs_entry_id": id,
                "rs_data": {
                    "rp_s1": id * 2,
                    "rp_s2": id * 2,
                    "rp_dst": id * 2,
                    "rob_id": id,
                    "exec_fn": {
                        "op_type": 1,
                        "funct3": 2,
                        "funct7": 3,
                    },
                    "s1_val": id,
                    "s2_val": id,
                    "imm": id,
                    "pc": id,
                },
            }
            for id in range(2**self.rs_entries_bits)
        ]
        self.check_list = create_check_list(self.rs_entries_bits, self.insert_list)

        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.simulation_process)

    def simulation_process(self):
        # After each insert, entry should be marked as full
        for record in self.insert_list:
            yield from self.m.insert.call(record)
        yield Settle()

        # Check data integrity
        for expected, record in zip(self.check_list, self.m._dut.data):
            assert expected == (yield from get_outputs(record))

        # Take first instruction
        assert (yield self.m._dut.get_ready_list[0].ready) == 1
        data = yield from self.m.take.call(rs_entry_id=0)
        for key in data:
            assert data[key] == self.check_list[0]["rs_data"][key]
        yield Settle()
        assert (yield self.m._dut.get_ready_list[0].ready) == 0

        # Update second instuction and take it
        reg_id = 2
        value_spx = 1
        yield from self.m.update.call(reg_id=reg_id, reg_val=value_spx)
        yield Settle()
        assert (yield self.m._dut.get_ready_list[0].ready) == 1
        data = yield from self.m.take.call(rs_entry_id=1)
        for key in data:
            assert data[key] == self.check_list[1]["rs_data"][key]
        yield Settle()
        assert (yield self.m._dut.get_ready_list[0].ready) == 0

        # Insert two new ready instructions and take them
        reg_id = 0
        value_spx = 3030
        entry_data = {
            "rp_s1": reg_id,
            "rp_s2": reg_id,
            "rp_dst": 1,
            "rob_id": 12,
            "exec_fn": {
                "op_type": 1,
                "funct3": 2,
                "funct7": 3,
            },
            "s1_val": 0,
            "s2_val": 0,
            "imm": 1,
            "pc": 40,
        }

        for index in range(2):
            yield from self.m.insert.call(rs_entry_id=index, rs_data=entry_data)
            yield Settle()
            assert (yield self.m._dut.get_ready_list[0].ready) == 1
            assert (yield self.m._dut.data_ready[index]) == 1

        data = yield from self.m.take.call(rs_entry_id=0)
        for key in data:
            assert data[key] == entry_data[key]
        yield Settle()
        assert (yield self.m._dut.get_ready_list[0].ready) == 1

        data = yield from self.m.take.call(rs_entry_id=1)
        for key in data:
            assert data[key] == entry_data[key]
        yield Settle()
        assert (yield self.m._dut.get_ready_list[0].ready) == 0


class TestRSMethodGetReadyList(TestCaseWithSimulator):
    def test_get_ready_list(self):
        self.gen_params = GenParams(test_core_config)
        self.rs_entries_bits = self.gen_params.max_rs_entries_bits
        self.m = SimpleTestCircuit(RS(self.gen_params, 2**self.rs_entries_bits, 0, None))
        self.insert_list = [
            {
                "rs_entry_id": id,
                "rs_data": {
                    "rp_s1": id // 2,
                    "rp_s2": id // 2,
                    "rp_dst": id * 2,
                    "rob_id": id,
                    "exec_fn": {
                        "op_type": 1,
                        "funct3": 2,
                        "funct7": 3,
                    },
                    "s1_val": id,
                    "s2_val": id,
                    "imm": id,
                    "pc": id,
                },
            }
            for id in range(2**self.rs_entries_bits)
        ]
        self.check_list = create_check_list(self.rs_entries_bits, self.insert_list)

        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.simulation_process)

    def simulation_process(self):
        # After each insert, entry should be marked as full
        for record in self.insert_list:
            yield from self.m.insert.call(record)
        yield Settle()

        # Check ready vector integrity
        ready_list = (yield from self.m.get_ready_list[0].call())["ready_list"]
        assert ready_list == 0b0011

        # Take first record and check ready vector integrity
        yield from self.m.take.call(rs_entry_id=0)
        yield Settle()
        ready_list = (yield from self.m.get_ready_list[0].call())["ready_list"]
        assert ready_list == 0b0010

        # Take second record and check ready vector integrity
        yield from self.m.take.call(rs_entry_id=1)
        yield Settle()
        option_ready_list = yield from self.m.get_ready_list[0].call_try()
        assert option_ready_list is None


class TestRSMethodTwoGetReadyLists(TestCaseWithSimulator):
    def test_two_get_ready_lists(self):
        self.gen_params = GenParams(test_core_config)
        self.rs_entries = self.gen_params.max_rs_entries
        self.rs_entries_bits = self.gen_params.max_rs_entries_bits
        self.m = SimpleTestCircuit(
            RS(self.gen_params, 2**self.rs_entries_bits, 0, [[OpType(1), OpType(2)], [OpType(3), OpType(4)]])
        )
        self.insert_list = [
            {
                "rs_entry_id": id,
                "rs_data": {
                    "rp_s1": 0,
                    "rp_s2": 0,
                    "rp_dst": id * 2,
                    "rob_id": id,
                    "exec_fn": {
                        "op_type": OpType(id + 1),
                        "funct3": 2,
                        "funct7": 3,
                    },
                    "s1_val": id,
                    "s2_val": id,
                    "imm": id,
                },
            }
            for id in range(self.rs_entries)
        ]
        self.check_list = create_check_list(self.rs_entries_bits, self.insert_list)

        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.simulation_process)

    def simulation_process(self):
        # After each insert, entry should be marked as full
        for record in self.insert_list:
            yield from self.m.insert.call(record)
        yield Settle()

        masks = [0b0011, 0b1100]

        for i in range(self.m._dut.rs_entries + 1):
            # Check ready vectors' integrity
            for j in range(2):
                ready_list = yield from self.m.get_ready_list[j].call_try()
                if masks[j]:
                    assert ready_list == {"ready_list": masks[j]}
                else:
                    assert ready_list is None

            # Take a record
            if i == self.m._dut.rs_entries:
                break
            yield from self.m.take.call(rs_entry_id=i)
            yield Settle()

            masks = [mask & ~(1 << i) for mask in masks]
