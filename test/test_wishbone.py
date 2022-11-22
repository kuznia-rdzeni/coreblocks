# Testbench for WishboneMaster, WishboneMuxer and WishboneArbiter

import random

from coreblocks.wishbone import *

from coreblocks.transactions import TransactionModule
from coreblocks.transactions.lib import AdapterTrans

from .common import *


class WishboneInterfaceWrapper:
    def __init__(self, wishbone_record):
        self.wb = wishbone_record

    def master_set(self, addr, data, we):
        yield self.wb.dat_w.eq(data)
        yield self.wb.adr.eq(addr)
        yield self.wb.we.eq(we)
        yield self.wb.cyc.eq(1)
        yield self.wb.stb.eq(1)

    def master_release(self, release_cyc=1):
        yield self.wb.stb.eq(0)
        if release_cyc:
            yield self.wb.cyc.eq(0)

    def master_verify(self, exp_data=0):
        assert (yield self.wb.ack)
        assert (yield self.wb.dat_r) == exp_data

    def slave_wait(self):
        while not ((yield self.wb.stb) and (yield self.wb.cyc)):
            yield

    def slave_verify(self, exp_addr, exp_data, exp_we, exp_sel=0):
        assert (yield self.wb.stb) and (yield self.wb.cyc)

        assert (yield self.wb.adr) == exp_addr
        assert (yield self.wb.we == exp_we)
        assert (yield self.wb.sel == exp_sel)
        if exp_we:
            assert (yield self.wb.dat_w) == exp_data

    def slave_respond(self, data, ack=1, err=0, rty=0):
        assert (yield self.wb.stb) and (yield self.wb.cyc)

        yield self.wb.dat_r.eq(data)
        yield self.wb.ack.eq(ack)
        yield self.wb.err.eq(err)
        yield self.wb.rty.eq(rty)
        yield
        yield self.wb.ack.eq(0)
        yield self.wb.err.eq(0)
        yield self.wb.rty.eq(0)


class TestWishboneMaster(TestCaseWithSimulator):
    class WishboneMasterTestModule(Elaboratable):
        def __init__(self):
            pass

        def elaborate(self, plaform):
            m = Module()
            tm = TransactionModule(m)
            m.submodules.wbm = self.wbm = wbm = WishboneMaster(WishboneParameters())
            m.submodules.rqa = self.requestAdapter = TestbenchIO(AdapterTrans(wbm.request))
            m.submodules.rsa = self.resultAdapter = TestbenchIO(AdapterTrans(wbm.result))
            return tm

    def test_manual(self):
        twbm = TestWishboneMaster.WishboneMasterTestModule()

        def process():
            wbm = twbm.wbm
            wwb = WishboneInterfaceWrapper(wbm.wbMaster)

            # read request
            yield from twbm.requestAdapter.call({"addr": 2, "data": 0, "we": 0, "sel": 1})
            yield
            assert not (yield wbm.request.ready)
            yield from wwb.slave_verify(2, 0, 0, 1)
            yield from wwb.slave_respond(8)
            resp = yield from twbm.resultAdapter.call()
            assert (resp["data"]) == 8

            # write request
            yield from twbm.requestAdapter.call({"addr": 3, "data": 5, "we": 1, "sel": 0})
            yield
            yield from wwb.slave_verify(3, 5, 1, 0)
            yield from wwb.slave_respond(0)
            yield from twbm.resultAdapter.call()

            # RTY and ERR responese
            yield from twbm.requestAdapter.call({"addr": 2, "data": 0, "we": 0, "sel": 0})
            yield
            yield from wwb.slave_wait()
            yield from wwb.slave_verify(2, 0, 0, 0)
            yield from wwb.slave_respond(1, ack=0, err=0, rty=1)
            yield
            assert not (yield wwb.wb.stb)
            assert not (yield wbm.result.ready)  # verify cycle restart
            yield from wwb.slave_wait()
            yield from wwb.slave_verify(2, 0, 0, 0)
            yield from wwb.slave_respond(1, ack=1, err=1, rty=0)
            resp = yield from twbm.resultAdapter.call()
            assert resp["data"] == 1
            assert resp["err"]

        with self.runSimulation(twbm) as sim:
            sim.add_sync_process(process)


class TestWishboneMuxer(TestCaseWithSimulator):
    def test_manual(self):
        wb_master = WishboneInterfaceWrapper(Record(WishboneLayout(WishboneParameters()).wb_layout))
        num_slaves = 4
        slaves = [WishboneInterfaceWrapper(Record.like(wb_master.wb, name=f"sl{i}")) for i in range(num_slaves)]
        mux = WishboneMuxer(wb_master.wb, [s.wb for s in slaves], Signal(num_slaves))

        def process():
            # check full communiaction
            yield from wb_master.master_set(2, 0, 1)
            yield mux.sselTGA.eq(0b0001)
            yield
            yield from slaves[0].slave_verify(2, 0, 1)
            assert not (yield slaves[1].wb.stb)
            yield from slaves[0].slave_respond(4)
            yield from wb_master.master_verify(4)
            yield from wb_master.master_release(release_cyc=0)
            yield
            # select without releasing cyc (only on stb)
            yield from wb_master.master_set(3, 0, 0)
            yield mux.sselTGA.eq(0b0010)
            yield
            assert not (yield slaves[0].wb.stb)
            yield from slaves[1].slave_verify(3, 0, 0)
            yield from slaves[1].slave_respond(5)
            yield from wb_master.master_verify(5)
            yield from wb_master.master_release()
            yield

            # normal selection
            yield from wb_master.master_set(6, 0, 0)
            yield mux.sselTGA.eq(0b1000)
            yield
            yield from slaves[3].slave_verify(6, 0, 0)
            yield from slaves[3].slave_respond(1)
            yield from wb_master.master_verify(1)

        with self.runSimulation(mux) as sim:
            sim.add_sync_process(process)


class TestWishboneAribiter(TestCaseWithSimulator):
    def test_manual(self):
        slave = WishboneInterfaceWrapper(Record(WishboneLayout(WishboneParameters()).wb_layout))
        masters = [WishboneInterfaceWrapper(Record.like(slave.wb, name=f"mst{i}")) for i in range(2)]
        arb = WishboneArbiter(slave.wb, [m.wb for m in masters])

        def process():
            yield from masters[0].master_set(2, 3, 1)
            yield from slave.slave_wait()
            yield from slave.slave_verify(2, 3, 1)
            yield from masters[1].master_set(1, 4, 1)
            yield from slave.slave_respond(0)

            yield from masters[0].master_verify()
            assert not (yield masters[1].wb.ack)
            yield from masters[0].master_release()
            yield

            # check if bus is granted to next master if previous ends cycle
            yield from slave.slave_wait()
            yield from slave.slave_verify(1, 4, 1)
            yield from slave.slave_respond(0)
            yield from masters[1].master_verify()
            assert not (yield masters[0].wb.ack)
            yield from masters[1].master_release()
            yield

            # check round robin behaviour (2 masters requesting *2)
            yield from masters[0].master_set(1, 0, 0)
            yield from masters[1].master_set(2, 0, 0)
            yield from slave.slave_wait()
            yield from slave.slave_verify(1, 0, 0)
            yield from slave.slave_respond(3)
            yield from masters[0].master_verify(3)
            yield from masters[0].master_release()
            yield from masters[1].master_release()
            yield
            assert not (yield slave.wb.cyc)

            yield from masters[0].master_set(1, 0, 0)
            yield from masters[1].master_set(2, 0, 0)
            yield from slave.slave_wait()
            yield from slave.slave_verify(2, 0, 0)
            yield from slave.slave_respond(0)
            yield from masters[1].master_verify()

            # check if releasing stb keeps grant
            yield from masters[1].master_release(release_cyc=0)
            yield
            yield from masters[1].master_set(3, 0, 0)
            yield from slave.slave_wait()
            yield from slave.slave_verify(3, 0, 0)
            yield from slave.slave_respond(0)
            yield from masters[1].master_verify()

        with self.runSimulation(arb) as sim:
            sim.add_sync_process(process)


class WishboneMemorySlaveCircuit(Elaboratable):
    def __init__(self, wb_params: WishboneParameters, mem_args: dict):
        self.wb_params = wb_params
        self.mem_args = mem_args

    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        m.submodules.mem_slave = self.mem_slave = WishboneMemorySlave(self.wb_params, **self.mem_args)
        m.submodules.mem_master = self.mem_master = WishboneMaster(self.wb_params)
        m.submodules.request = self.request = TestbenchIO(AdapterTrans(self.mem_master.request))
        m.submodules.result = self.result = TestbenchIO(AdapterTrans(self.mem_master.result))

        m.d.comb += self.mem_master.wbMaster.connect(self.mem_slave.bus)

        return tm


class TestWishboneMemorySlave(TestCaseWithSimulator):
    def setUp(self):
        self.memsize = 430  # test some weird depth
        self.iters = 300

        self.addr_width = (self.memsize - 1).bit_length()  # nearest log2 >= log2(memsize)
        self.wb_params = WishboneParameters(data_width=32, addr_width=self.addr_width, granularity=16)
        self.m = WishboneMemorySlaveCircuit(wb_params=self.wb_params, mem_args={"depth": self.memsize})

        self.sel_width = self.wb_params.data_width // self.wb_params.granularity

        random.seed(42)

    def test_randomized(self):
        def mem_op_process():
            mem_state = [0] * self.memsize

            for _ in range(self.iters):
                addr = random.randint(0, self.memsize - 1)
                data = random.randint(0, 2**self.wb_params.data_width - 1)
                write = random.randint(0, 1)
                sel = random.randint(0, 2**self.sel_width - 1)
                if write:
                    for i in range(self.sel_width):
                        if sel & (1 << i):
                            granularity_mask = (2**self.wb_params.granularity - 1) << (i * self.wb_params.granularity)
                            mem_state[addr] &= ~granularity_mask
                            mem_state[addr] |= data & granularity_mask

                yield from self.m.request.call({"addr": addr, "data": data, "we": write, "sel": sel})
                res = yield from self.m.result.call()
                if write:
                    self.assertEqual((yield self.m.mem_slave.mem[addr]), mem_state[addr])
                else:
                    self.assertEqual(res["data"], mem_state[addr])

        with self.runSimulation(self.m, max_cycles=1500) as sim:
            sim.add_sync_process(mem_op_process)
