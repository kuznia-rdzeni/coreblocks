from collections import deque
from amaranth import Elaboratable, Module
from amaranth.sim import Passive, Settle

from coreblocks.transactions import TransactionModule
from coreblocks.transactions.lib import AdapterTrans, FIFO

from ..common import TestCaseWithSimulator, TestbenchIO, test_gen_params

from coreblocks.frontend.fetch import Fetch
from coreblocks.params import GenParams, FetchLayouts

from random import Random

from coreblocks.peripherals.wishbone import WishboneMaster, WishboneParameters
from ..peripherals.test_wishbone import WishboneInterfaceWrapper


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
        self.verify_branch = TestbenchIO(AdapterTrans(self.fetch.verify_branch))

        self.io_in = WishboneInterfaceWrapper(self.wbm.wbMaster)

        m.submodules.fetch = self.fetch
        m.submodules.wbm = self.wbm
        m.submodules.io_out = self.io_out
        m.submodules.verify_branch = self.verify_branch
        m.submodules.fifo = fifo

        return tm


class TestFetch(TestCaseWithSimulator):
    def setUp(self) -> None:
        self.gp = test_gen_params("rv32i", start_pc=24)
        self.test_module = TestElaboratable(self.gp)
        self.instr_queue = deque()
        self.iterations = 500

    def wishbone_slave(self):
        rand = Random(0)
        next_pc = self.gp.start_pc

        yield Passive()

        while True:
            yield from self.test_module.io_in.slave_wait()

            addr = self.gp.isa.ilen_bytes * (yield self.test_module.io_in.wb.adr)

            while rand.random() < 0.5:
                yield

            is_branch = rand.random() < 0.15

            # exclude branches and jumps
            data = rand.randint(0, 2**self.gp.isa.ilen - 1) & ~0b1110000
            next_pc = addr + self.gp.isa.ilen_bytes

            # randomize being a branch instruction
            if is_branch:
                data |= 0b1100000
                next_pc = rand.randint(0, (2**self.gp.isa.ilen - 1)) & ~0b11

            if rand.random() < 0.5:
                self.instr_queue.append(
                    {
                        "data": data,
                        "pc": addr,
                        "is_branch": is_branch,
                        "next_pc": next_pc,
                    }
                )
                yield from self.test_module.io_in.slave_respond(data)
            else:
                yield from self.test_module.io_in.slave_respond(data, err=1)

            yield Settle()

    def fetch_out_check(self):
        rand = Random(420)

        for i in range(self.iterations):
            try:
                instr = self.instr_queue.popleft()
                if instr["is_branch"]:
                    for _ in range(rand.randrange(10)):
                        yield
                    yield from self.test_module.verify_branch.call({"next_pc": instr["next_pc"]})

                v = yield from self.test_module.io_out.call()
                self.assertEqual((yield self.test_module.fetch.pc), instr["next_pc"])
                self.assertEqual(v["data"], instr["data"])
            except IndexError:
                yield

    def test(self):

        with self.run_simulation(self.test_module) as sim:
            sim.add_sync_process(self.wishbone_slave)
            sim.add_sync_process(self.fetch_out_check)
