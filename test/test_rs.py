from amaranth import Elaboratable, Module

from coreblocks.transactions import TransactionModule
from coreblocks.transactions.lib import AdapterTrans

from common import TestCaseWithSimulator, TestbenchIO

from coreblocks.rs import RS
from coreblocks.genparams import GenParams


class TestElaboratable(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.gp = gen_params

    def elaborate(self, platform):
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
            for id in range(self.gp.rs_entries_bits**2)
        ]

        with self.runSimulation(self.m) as sim:
            sim.add_clock(1e-6)
            sim.add_sync_process(self.insert_process)

    def insert_process(self):
        for record in self.insert_list:
            yield from self.m.io_insert.call(record)


class TestRSMethodSelect(TestCaseWithSimulator):
    def test_select(self):
        pass


class TestRSMethodUpdate(TestCaseWithSimulator):
    def test_update(self):
        pass


class TestRSMethodPush(TestCaseWithSimulator):
    def test_push(self):
        pass


class TestRSFull(TestCaseWithSimulator):
    def test_full(self):
        pass
