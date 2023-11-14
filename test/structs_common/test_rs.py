from typing import Iterable, Optional
from amaranth import Elaboratable, Module
from amaranth.sim import Settle

from transactron.lib import AdapterTrans

from ..common import TestCaseWithSimulator, TestbenchIO, get_outputs

from coreblocks.structs_common.rs import RS
from coreblocks.params import *
from coreblocks.params.configurations import test_core_config


def create_check_list(rs_entries_bits: int, insert_list: list[dict]) -> list[dict]:
    check_list = [
        {"rs_data": None, "rec_ready": 0, "rec_reserved": 0, "rec_full": 0} for _ in range(2**rs_entries_bits)
    ]

    for params in insert_list:
        entry_id = params["rs_entry_id"]
        check_list[entry_id]["rs_data"] = params["rs_data"]
        check_list[entry_id]["rec_ready"] = 1 if params["rs_data"]["rp_s1"] | params["rs_data"]["rp_s2"] == 0 else 0
        check_list[entry_id]["rec_full"] = 1
        check_list[entry_id]["rec_reserved"] = 1

    return check_list


class TestElaboratable(Elaboratable):
    def __init__(self, gen_params: GenParams, ready_for: Optional[Iterable[Iterable[OpType]]] = None) -> None:
        self.gp = gen_params
        self.ready_for = ready_for
        # test config GenParams specifies only one RS - it has the max number of entries
        self.rs_entries = self.gp.max_rs_entries
        self.rs_entries_bits = self.gp.max_rs_entries_bits

    def elaborate(self, platform) -> Module:
        m = Module()
        rs = RS(self.gp, 2**self.rs_entries_bits, self.ready_for)

        self.rs = rs
        self.io_select = TestbenchIO(AdapterTrans(rs.select))
        self.io_insert = TestbenchIO(AdapterTrans(rs.insert))
        self.io_update = TestbenchIO(AdapterTrans(rs.update))
        self.io_take = TestbenchIO(AdapterTrans(rs.take))
        self.io_get_ready_list = [TestbenchIO(AdapterTrans(get_ready_list)) for get_ready_list in rs.get_ready_list]

        m.submodules.rs = rs
        m.submodules.io_select = self.io_select
        m.submodules.io_insert = self.io_insert
        m.submodules.io_update = self.io_update
        m.submodules.io_take = self.io_take
        for n, io_get_ready_list in enumerate(self.io_get_ready_list):
            m.submodules[f"io_get_ready_list_{n}"] = io_get_ready_list

        return m


class TestRSMethodInsert(TestCaseWithSimulator):
    def test_insert(self):
        self.gp = GenParams(test_core_config)
        self.m = TestElaboratable(self.gp)
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
            for id in range(2**self.m.rs_entries_bits)
        ]
        self.check_list = create_check_list(self.m.rs_entries_bits, self.insert_list)

        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.simulation_process)

    def simulation_process(self):
        # After each insert, entry should be marked as full
        for index, record in enumerate(self.insert_list):
            self.assertEqual((yield self.m.rs.data[index].rec_full), 0)
            yield from self.m.io_insert.call(record)
            yield Settle()
            self.assertEqual((yield self.m.rs.data[index].rec_full), 1)
        yield Settle()

        # Check data integrity
        for expected, record in zip(self.check_list, self.m.rs.data):
            self.assertEqual(expected, (yield from get_outputs(record)))


class TestRSMethodSelect(TestCaseWithSimulator):
    def test_select(self):
        self.gp = GenParams(test_core_config)
        self.m = TestElaboratable(self.gp)
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
            for id in range(2**self.m.rs_entries_bits - 1)
        ]
        self.check_list = create_check_list(self.m.rs_entries_bits, self.insert_list)

        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.simulation_process)

    def simulation_process(self):
        # In the beginning the select method should be ready and id should be selectable
        for index, record in enumerate(self.insert_list):
            self.assertEqual((yield self.m.rs.select.ready), 1)
            self.assertEqual((yield from self.m.io_select.call())["rs_entry_id"], index)
            yield Settle()
            self.assertEqual((yield self.m.rs.data[index].rec_reserved), 1)
            yield from self.m.io_insert.call(record)
        yield Settle()

        # Check if RS state is as expected
        for expected, record in zip(self.check_list, self.m.rs.data):
            self.assertEqual((yield record.rec_full), expected["rec_full"])
            self.assertEqual((yield record.rec_ready), expected["rec_ready"])
            self.assertEqual((yield record.rec_reserved), expected["rec_reserved"])

        # Reserve the last entry, then select ready should be false
        self.assertEqual((yield self.m.rs.select.ready), 1)
        self.assertEqual((yield from self.m.io_select.call())["rs_entry_id"], 3)
        yield Settle()
        self.assertEqual((yield self.m.rs.select.ready), 0)

        # After take, select ready should be true, with 0 index returned
        yield from self.m.io_take.call()
        yield Settle()
        self.assertEqual((yield self.m.rs.select.ready), 1)
        self.assertEqual((yield from self.m.io_select.call())["rs_entry_id"], 0)

        # After reservation, select is false again
        yield Settle()
        self.assertEqual((yield self.m.rs.select.ready), 0)


class TestRSMethodUpdate(TestCaseWithSimulator):
    def test_update(self):
        self.gp = GenParams(test_core_config)
        self.m = TestElaboratable(self.gp)
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
            for id in range(2**self.m.rs_entries_bits)
        ]
        self.check_list = create_check_list(self.m.rs_entries_bits, self.insert_list)

        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.simulation_process)

    def simulation_process(self):
        # Insert all reacords
        for record in self.insert_list:
            yield from self.m.io_insert.call(record)
        yield Settle()

        # Check data integrity
        for expected, record in zip(self.check_list, self.m.rs.data):
            self.assertEqual(expected, (yield from get_outputs(record)))

        # Update second entry first SP, instruction should be not ready
        value_sp1 = 1010
        self.assertEqual((yield self.m.rs.data[1].rec_ready), 0)
        yield from self.m.io_update.call(reg_id=2, reg_val=value_sp1)
        yield Settle()
        self.assertEqual((yield self.m.rs.data[1].rs_data.rp_s1), 0)
        self.assertEqual((yield self.m.rs.data[1].rs_data.s1_val), value_sp1)
        self.assertEqual((yield self.m.rs.data[1].rec_ready), 0)

        # Update second entry second SP, instruction should be ready
        value_sp2 = 2020
        yield from self.m.io_update.call(reg_id=3, reg_val=value_sp2)
        yield Settle()
        self.assertEqual((yield self.m.rs.data[1].rs_data.rp_s2), 0)
        self.assertEqual((yield self.m.rs.data[1].rs_data.s2_val), value_sp2)
        self.assertEqual((yield self.m.rs.data[1].rec_ready), 1)

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
            yield from self.m.io_insert.call(rs_entry_id=index, rs_data=data)
            yield Settle()
            self.assertEqual((yield self.m.rs.data[index].rec_ready), 0)

        yield from self.m.io_update.call(reg_id=reg_id, reg_val=value_spx)
        yield Settle()
        for index in range(2):
            self.assertEqual((yield self.m.rs.data[index].rs_data.rp_s1), 0)
            self.assertEqual((yield self.m.rs.data[index].rs_data.rp_s2), 0)
            self.assertEqual((yield self.m.rs.data[index].rs_data.s1_val), value_spx)
            self.assertEqual((yield self.m.rs.data[index].rs_data.s2_val), value_spx)
            self.assertEqual((yield self.m.rs.data[index].rec_ready), 1)


class TestRSMethodTake(TestCaseWithSimulator):
    def test_take(self):
        self.gp = GenParams(test_core_config)
        self.m = TestElaboratable(self.gp)
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
            for id in range(2**self.m.rs_entries_bits)
        ]
        self.check_list = create_check_list(self.m.rs_entries_bits, self.insert_list)

        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.simulation_process)

    def simulation_process(self):
        # After each insert, entry should be marked as full
        for record in self.insert_list:
            yield from self.m.io_insert.call(record)
        yield Settle()

        # Check data integrity
        for expected, record in zip(self.check_list, self.m.rs.data):
            self.assertEqual(expected, (yield from get_outputs(record)))

        # Take first instruction
        self.assertEqual((yield self.m.rs.take.ready), 1)
        data = yield from self.m.io_take.call(rs_entry_id=0)
        for key in data:
            self.assertEqual(data[key], self.check_list[0]["rs_data"][key])
        yield Settle()
        self.assertEqual((yield self.m.rs.take.ready), 0)

        # Update second instuction and take it
        reg_id = 2
        value_spx = 1
        yield from self.m.io_update.call(reg_id=reg_id, reg_val=value_spx)
        yield Settle()
        self.assertEqual((yield self.m.rs.take.ready), 1)
        data = yield from self.m.io_take.call(rs_entry_id=1)
        for key in data:
            self.assertEqual(data[key], self.check_list[1]["rs_data"][key])
        yield Settle()
        self.assertEqual((yield self.m.rs.take.ready), 0)

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
            yield from self.m.io_insert.call(rs_entry_id=index, rs_data=entry_data)
            yield Settle()
            self.assertEqual((yield self.m.rs.data[index].rec_ready), 1)
            self.assertEqual((yield self.m.rs.take.ready), 1)

        data = yield from self.m.io_take.call(rs_entry_id=0)
        for key in data:
            self.assertEqual(data[key], entry_data[key])
        yield Settle()
        self.assertEqual((yield self.m.rs.take.ready), 1)

        data = yield from self.m.io_take.call(rs_entry_id=1)
        for key in data:
            self.assertEqual(data[key], entry_data[key])
        yield Settle()
        self.assertEqual((yield self.m.rs.take.ready), 0)


class TestRSMethodGetReadyList(TestCaseWithSimulator):
    def test_get_ready_list(self):
        self.gp = GenParams(test_core_config)
        self.m = TestElaboratable(self.gp)
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
            for id in range(2**self.m.rs_entries_bits)
        ]
        self.check_list = create_check_list(self.m.rs_entries_bits, self.insert_list)

        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.simulation_process)

    def simulation_process(self):
        # After each insert, entry should be marked as full
        for record in self.insert_list:
            yield from self.m.io_insert.call(record)
        yield Settle()

        # Check ready vector integrity
        ready_list = (yield from self.m.io_get_ready_list[0].call())["ready_list"]
        self.assertEqual(ready_list, 0b0011)

        # Take first record and check ready vector integrity
        yield from self.m.io_take.call(rs_entry_id=0)
        yield Settle()
        ready_list = (yield from self.m.io_get_ready_list[0].call())["ready_list"]
        self.assertEqual(ready_list, 0b0010)

        # Take second record and check ready vector integrity
        yield from self.m.io_take.call(rs_entry_id=1)
        yield Settle()
        option_ready_list = yield from self.m.io_get_ready_list[0].call_try()
        self.assertIsNone(option_ready_list)


class TestRSMethodTwoGetReadyLists(TestCaseWithSimulator):
    def test_two_get_ready_lists(self):
        self.gp = GenParams(test_core_config)
        self.m = TestElaboratable(self.gp, [[OpType(1), OpType(2)], [OpType(3), OpType(4)]])
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
            for id in range(self.m.rs_entries)
        ]
        self.check_list = create_check_list(self.m.rs_entries_bits, self.insert_list)

        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.simulation_process)

    def simulation_process(self):
        # After each insert, entry should be marked as full
        for record in self.insert_list:
            yield from self.m.io_insert.call(record)
        yield Settle()

        masks = [0b0011, 0b1100]

        for i in range(self.m.rs.rs_entries + 1):
            # Check ready vectors' integrity
            for j in range(2):
                ready_list = yield from self.m.io_get_ready_list[j].call_try()
                if masks[j]:
                    self.assertEqual(ready_list, {"ready_list": masks[j]})
                else:
                    self.assertIsNone(ready_list)

            # Take a record
            if i == self.m.rs.rs_entries:
                break
            yield from self.m.io_take.call(rs_entry_id=i)
            yield Settle()

            masks = [mask & ~(1 << i) for mask in masks]
