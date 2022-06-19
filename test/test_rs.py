from amaranth import Elaboratable, Module
from amaranth.sim import Settle

from coreblocks.transactions import TransactionModule
from coreblocks.transactions.lib import AdapterTrans

from .common import TestCaseWithSimulator, TestbenchIO

from coreblocks.rs import RS
from coreblocks.genparams import GenParams

from threading import Lock
from typing import Any


def create_check_list(gp: GenParams, insert_list: list[dict]) -> list[dict]:
    check_list = [
        {"rs_data": None, "rec_ready": 0, "rec_reserved": 0, "rec_full": 0} for _ in range(2**gp.rs_entries_bits)
    ]

    for params in insert_list:
        entry_id = params["rs_entry_id"]
        check_list[entry_id]["rs_data"] = params["rs_data"]
        check_list[entry_id]["rec_ready"] = 1 if params["rs_data"]["rp_s1"] | params["rs_data"]["rp_s2"] == 0 else 0
        check_list[entry_id]["rec_full"] = 1
        check_list[entry_id]["rec_reserved"] = 1

    return check_list


class TestElaboratable(Elaboratable):
    def __init__(self, gen_params: GenParams) -> None:
        self.gp = gen_params

    def elaborate(self, platform) -> TransactionModule:
        m = Module()
        tm = TransactionModule(m)
        rs = RS(self.gp)

        self.rs = rs
        self.io_select = TestbenchIO(AdapterTrans(rs.select))
        self.io_insert = TestbenchIO(AdapterTrans(rs.insert))
        self.io_update = TestbenchIO(AdapterTrans(rs.update))
        self.io_push = TestbenchIO(AdapterTrans(rs.push))

        m.submodules.rs = rs
        m.submodules.io_select = self.io_select
        m.submodules.io_insert = self.io_insert
        m.submodules.io_update = self.io_update
        m.submodules.io_push = self.io_push

        return tm


class TestRSMethodInsert(TestCaseWithSimulator):
    def test_insert(self):
        self.gp = GenParams("rv32i", phys_regs_bits=7, rob_entries_bits=7, rs_entries_bits=2)
        self.m = TestElaboratable(self.gp)
        self.done_lock = Lock()
        self.done_lock.acquire()
        self.insert_list = [
            {
                "rs_entry_id": id,
                "rs_data": {
                    "rp_s1": id * 2,
                    "rp_s2": id * 2 + 1,
                    "rp_dst": id * 2,
                    "rob_id": id,
                    "opcode": 1,
                    "s1_val": id,
                    "s2_val": id,
                },
            }
            for id in range(2**self.gp.rs_entries_bits)
        ]
        self.check_list = create_check_list(self.gp, self.insert_list)

        with self.runSimulation(self.m) as sim:
            sim.add_clock(1e-6)
            sim.add_sync_process(self.insert_process)
            sim.add_sync_process(self.check_process)

    def insert_process(self):
        for record in self.insert_list:
            yield from self.m.io_insert.call(record)
        self.done_lock.release()

    def check_process(self):
        while self.done_lock.locked():
            yield

        yield Settle()
        for expected, record in zip(self.check_list, self.m.rs.data):
            self.assertEqual((yield record.rec_full), expected["rec_full"])
            self.assertEqual((yield record.rec_ready), expected["rec_ready"])
            self.assertEqual((yield record.rec_reserved), expected["rec_reserved"])
            if expected["rs_data"]:
                for key in expected["rs_data"]:
                    self.assertEqual((yield getattr(record.rs_data, key)), expected["rs_data"][key])


class TestRSMethodSelect(TestCaseWithSimulator):
    def test_select(self):
        self.gp = GenParams("rv32i", phys_regs_bits=7, rob_entries_bits=7, rs_entries_bits=2)
        self.m = TestElaboratable(self.gp)
        self.done_lock = Lock()
        self.done_lock.acquire()
        self.insert_list = [
            {
                "rs_entry_id": id,
                "rs_data": {
                    "rp_s1": id * 2,
                    "rp_s2": id * 2,
                    "rp_dst": id * 2,
                    "rob_id": id,
                    "opcode": 1,
                    "s1_val": id,
                    "s2_val": id,
                },
            }
            for id in range(2**self.gp.rs_entries_bits - 1)
        ]
        self.check_list = create_check_list(self.gp, self.insert_list)

        with self.runSimulation(self.m) as sim:
            sim.add_clock(1e-6)
            sim.add_sync_process(self.insert_process)
            sim.add_sync_process(self.check_process)

    def insert_process(self):
        for record in self.insert_list:
            yield from self.m.io_insert.call(record)
        self.done_lock.release()

    def check_process(self):
        self.assertEqual((yield self.m.rs.select.ready), 1)
        self.assertEqual((yield from self.m.io_select.call())["rs_entry_id"], 0)

        while self.done_lock.locked():
            yield
        yield Settle()

        for expected, record in zip(self.check_list, self.m.rs.data):
            self.assertEqual((yield record.rec_full), expected["rec_full"])
            self.assertEqual((yield record.rec_ready), expected["rec_ready"])
            self.assertEqual((yield record.rec_reserved), expected["rec_reserved"])
            if expected["rs_data"]:
                for key in expected["rs_data"]:
                    self.assertEqual((yield getattr(record.rs_data, key)), expected["rs_data"][key])
        self.assertEqual((yield self.m.rs.select.ready), 1)
        self.assertEqual((yield from self.m.io_select.call())["rs_entry_id"], 3)


class TestRSMethodUpdate(TestCaseWithSimulator):
    def test_update(self):
        pass


class TestRSMethodPush(TestCaseWithSimulator):
    def test_push(self):
        pass


class TestRSFull(TestCaseWithSimulator):
    def test_full(self):
        pass
