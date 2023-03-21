from collections import deque
from parameterized import parameterized_class
import random

from amaranth import Elaboratable, Module
from amaranth.sim import Passive, Settle

from coreblocks.transactions import TransactionModule
from coreblocks.transactions.lib import AdapterTrans, Adapter
from coreblocks.frontend.icache import SimpleWBCacheRefiller, ICacheParameters, ICache
from coreblocks.params import GenParams, ICacheLayouts
from coreblocks.peripherals.wishbone import WishboneMaster, WishboneParameters

from ..common import TestCaseWithSimulator, TestbenchIO, test_gen_params
from ..peripherals.test_wishbone import WishboneInterfaceWrapper


class SimpleWBCacheRefillerTestCircuit(Elaboratable):
    def __init__(self, gen_params: GenParams, cache_params: ICacheParameters):
        self.gp = gen_params
        self.cp = cache_params

    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        wb_params = WishboneParameters(
            data_width=self.gp.isa.xlen,
            addr_width=self.gp.isa.xlen,
        )
        self.wb_master = WishboneMaster(wb_params)

        self.refiller = SimpleWBCacheRefiller(self.gp, self.cp, self.wb_master)

        self.start_refill = TestbenchIO(AdapterTrans(self.refiller.start_refill))
        self.accept_refill = TestbenchIO(AdapterTrans(self.refiller.accept_refill))

        m.submodules.wb_master = self.wb_master
        m.submodules.refiller = self.refiller
        m.submodules.start_refill = self.start_refill
        m.submodules.accept_refill = self.accept_refill

        self.wb_ctrl = WishboneInterfaceWrapper(self.wb_master.wbMaster)

        return tm


@parameterized_class(
    ("name", "block_size"),
    [
        ("blk_size16", 16),
        ("blk_size32", 32),
        ("blk_size64", 64),
    ],
)
class TestSimpleWBCacheRefiller(TestCaseWithSimulator):
    block_size: int

    def setUp(self) -> None:
        self.gp = test_gen_params("rv32i")
        self.cp = ICacheParameters(num_of_ways=1, num_of_sets=1, block_size_bytes=self.block_size)
        self.test_module = SimpleWBCacheRefillerTestCircuit(self.gp, self.cp)

        self.words_per_block = self.block_size // 4

        random.seed(42)

        self.bad_addresses = set()
        self.mem = dict()

        self.requests = deque()
        for i in range(10):
            # Make the address aligned to the beginning of a cache line
            addr = random.randint(0, 2**32 - 1) & ~((1 << self.cp.offset_bits) - 1)
            self.requests.append(addr)

            if random.random() < 0.1:
                # Choose an address in this cache line to be erroneous
                bad_addr = addr + random.randint(0, (1 << self.cp.offset_bits) - 1)

                # Make the address aligned to the machine word size
                bad_addr = bad_addr & ~(0b11)

                self.bad_addresses.add(bad_addr)

    def wishbone_slave(self):
        yield Passive()

        while True:
            yield from self.test_module.wb_ctrl.slave_wait()

            # Wishbone is addressing words, so to get the real address we multiply it by 4
            addr = (yield self.test_module.wb_ctrl.wb.adr) << 2

            while random.random() < 0.5:
                yield

            err = 1 if addr in self.bad_addresses else 0

            data = random.randint(0, 2**32 - 1)
            self.mem[addr] = data

            yield from self.test_module.wb_ctrl.slave_respond(data, err=err)

            yield Settle()

    def refiller_process(self):
        while self.requests:
            req_addr = self.requests.pop()
            yield from self.test_module.start_refill.call({"addr": req_addr})

            for i in range(self.words_per_block):
                ret = yield from self.test_module.accept_refill.call()

                cur_addr = req_addr + i * 4

                self.assertEqual(ret["addr"], cur_addr)

                if cur_addr in self.bad_addresses:
                    self.assertEqual(ret["error"], 1)
                    self.assertEqual(ret["last"], 1)
                    break

                self.assertEqual(ret["data"], self.mem[ret["addr"]])
                self.assertEqual(ret["error"], 0)

                last = 1 if i == self.words_per_block - 1 else 0
                self.assertEqual(ret["last"], last)

    def test(self):
        with self.run_simulation(self.test_module) as sim:
            sim.add_sync_process(self.wishbone_slave)
            sim.add_sync_process(self.refiller_process)


class ICacheTestCircuit(Elaboratable):
    def __init__(self, gen_params: GenParams, cache_params: ICacheParameters):
        self.gp = gen_params
        self.cp = cache_params

    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        # mocked cache refiller
        layouts = self.gp.get(ICacheLayouts)
        m.submodules.start_refill = self.start_refill = TestbenchIO(Adapter(i=layouts.start_refill))
        m.submodules.accept_refill = self.accept_refill = TestbenchIO(Adapter(o=layouts.accept_refill))

        self.cache = ICache(self.gp, self.cp, self.start_refill.adapter.iface, self.accept_refill.adapter.iface)

        self.issue_req = TestbenchIO(AdapterTrans(self.cache.issue_req))
        self.accept_res = TestbenchIO(AdapterTrans(self.cache.accept_res))

        m.submodules.cache = self.cache
        m.submodules.issue_req = self.issue_req
        m.submodules.accept_res = self.accept_res

        return tm


@parameterized_class(
    ("name", "block_size"),
    [
        ("blk_size16", 16),
    ],
)
class TestICache(TestCaseWithSimulator):
    block_size: int

    def setUp(self) -> None:
        self.gp = test_gen_params("rv32i")
        self.cp = ICacheParameters(num_of_ways=1, num_of_sets=1, block_size_bytes=self.block_size)
        self.test_module = ICacheTestCircuit(self.gp, self.cp)

        random.seed(42)

    def refiller_process(self):
        yield Passive()

    def test(self):
        with self.run_simulation(self.test_module) as sim:
            sim.add_sync_process(self.refiller_process)
