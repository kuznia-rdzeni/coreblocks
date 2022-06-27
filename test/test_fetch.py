from collections import deque
from re import L
from amaranth import Elaboratable, Module
from amaranth.sim import Passive, Settle

from coreblocks.transactions import TransactionModule
from coreblocks.transactions.lib import AdapterTrans, FIFO

from .common import TestCaseWithSimulator, TestbenchIO

from coreblocks.fetch import Fetch
from coreblocks.genparams import GenParams
from coreblocks.layouts import FetchLayouts

from random import Random

from coreblocks.wishbone import WishboneMaster, WishboneParameters
from .test_wishbone import WishboneInterfaceWrapper


class TestElaboratable(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.gp = gen_params

    def elaborate(self, platform):

        m = Module()
        tm = TransactionModule(m)

        wb_params = WishboneParameters(
            data_width=self.gp.isa.ilen,
            addr_width=32,
        )

        self.wbm = WishboneMaster(wb_params)
        fifo = FIFO(self.gp.get(FetchLayouts).raw_instr, depth=2)
        self.io_out = TestbenchIO(AdapterTrans(fifo.read))
        self.fetch = Fetch(self.gp, self.wbm, fifo.write)

        self.io_in = WishboneInterfaceWrapper(self.wbm.wbMaster)

        m.submodules.fetch = self.fetch
        m.submodules.wbm = self.wbm
        m.submodules.io_out = self.io_out
        m.submodules.fifo = fifo

        return tm


class TestFetch(TestCaseWithSimulator):
    def setUp(self) -> None:
        self.gp = GenParams("rv32i", start_pc=24)
        self.test_module = TestElaboratable(self.gp)
        self.instr_queue = deque()

    def wishbone_slave(self):
        rand = Random(0)
        last_addr = self.gp.start_pc - (self.gp.isa.ilen_bytes)

        yield Passive()

        while True:
            yield from self.test_module.io_in.slave_wait()

            addr = yield self.test_module.io_in.wb.adr
            self.assertEqual(addr, last_addr + (self.gp.isa.ilen_bytes))

            while rand.random() < 0.5:
                yield

            data = rand.randint(0, 2**self.gp.isa.ilen - 1)

            if rand.random() < 0.5:
                self.instr_queue.append(data)
                yield from self.test_module.io_in.slave_respond(data)
                last_addr = addr
            else:
                yield from self.test_module.io_in.slave_respond(data, err=1)

            yield Settle()

    def fetch_out_check(self):
        for i in range(100):
            v = yield from self.test_module.io_out.call()
            self.assertEqual(v["data"], self.instr_queue.popleft())

    def test(self):

        with self.runSimulation(self.test_module) as sim:
            sim.add_sync_process(self.wishbone_slave)
            sim.add_sync_process(self.fetch_out_check)
