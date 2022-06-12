from re import L
from amaranth import Elaboratable, Module
from amaranth.sim import Passive

from coreblocks.transactions import TransactionModule
from coreblocks.transactions.lib import AdapterTrans, FIFO

from .common import TestCaseWithSimulator, TestbenchIO

from coreblocks.fetch import Fetch
from coreblocks.genparams import GenParams

from queue import Queue
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
        fifo = FIFO(self.wbm.resultLayout, depth=2)
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
        super().setUp()
        self.gp = GenParams("rv32i")
        self.test_module = TestElaboratable(self.gp)
        self.instr_queue = Queue()
        self.last_addr = -(self.gp.isa.ilen // 8)
        self.rand = Random(0)

    def wishbone_slave(self):

        yield Passive()

        while True:
            yield from self.test_module.io_in.slave_wait()

            addr = yield self.test_module.io_in.wb.adr
            # print(addr)
            self.assertEqual(addr, self.last_addr + (self.gp.isa.ilen // 8))

            if self.rand.random() < 0.5:
                data = self.rand.randint(0, self.gp.isa.ilen - 1)
                self.instr_queue.put(data)
                yield from self.test_module.io_in.slave_respond(data)
                self.last_addr = addr
            else:
                data = self.rand.randint(0, self.gp.isa.ilen - 1)
                yield from self.test_module.io_in.slave_respond(data, err=1)

            yield  # If this yield is removed the test fails, but it seems to me that it shouldn't.

    def fetch_out_check(self):
        for i in range(100):
            v = yield from self.test_module.io_out.call()
            # print(v)
            self.assertEqual(v["data"], self.instr_queue.get())

    def test(self):

        with self.runSimulation(self.test_module) as sim:
            sim.add_clock(1e-6)
            sim.add_sync_process(self.wishbone_slave)
            sim.add_sync_process(self.fetch_out_check)
