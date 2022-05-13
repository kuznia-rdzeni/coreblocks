# Testbench for WishboneMaster, WishboneMuxer and WishboneArbiter

from coreblocks.wishbone import *
from amaranth.sim import Simulator

from coreblocks.transactions import TransactionModule
from coreblocks.transactions.lib import AdapterTrans
from coreblocks.genparams import GenParams

from .common import *


class TestWishboneMaster(TestCaseWithSimulator):
    class WishboneMasterTestModule(Elaboratable):
        def __init__(self):
            pass

        def elaborate(self, plaform):
            m = Module()
            tm = TransactionModule(m)
            with tm.transactionContext():
                m.submodules.wbm = self.wbm = wbm = WishboneMaster(GenParams())
                m.submodules.rqa = self.requestAdapter = AdapterTrans(wbm.request, i=wbm.requestLayout)
                m.submodules.rsa = self.resultAdapter = AdapterTrans(wbm.result, o=wbm.resultLayout)
            return tm

    def test_manual(self):
        twbm = TestWishboneMaster.WishboneMasterTestModule()

        def process():
            wbm = twbm.wbm
            requestAdapter = twbm.requestAdapter
            resultAdapter = twbm.resultAdapter

            yield
            # reset cycle
            assert (yield wbm.wbMaster.rst)
            yield
            assert not (yield wbm.wbMaster.cyc)
            assert not (yield wbm.wbMaster.stb)
            yield
            # request read
            assert (yield wbm.request.ready)
            assert not (yield wbm.result.ready)
            yield requestAdapter.data_in.addr.eq(2)
            yield requestAdapter.data_in.we.eq(0)
            yield requestAdapter.en.eq(1)
            yield
            assert (yield requestAdapter.done)
            yield requestAdapter.en.eq(0)
            yield
            # assert making new request is unavaliable (parameters cannot change)
            # and check busy state
            assert not (yield wbm.request.ready)
            assert not (yield wbm.result.ready)
            yield
            assert (yield wbm.wbMaster.adr == 2)
            assert (yield wbm.wbMaster.cyc)
            assert (yield wbm.wbMaster.stb)
            assert not (yield wbm.wbMaster.we)
            yield
            assert (yield wbm.wbMaster.adr == 2)
            # simulate delayed response
            yield
            yield
            yield wbm.wbMaster.dat_r.eq(3)
            yield wbm.wbMaster.ack.eq(1)
            yield
            assert not (yield wbm.request.ready)
            assert not (yield wbm.result.ready)
            yield wbm.wbMaster.ack.eq(0)
            # response should be available in the next cycle
            yield resultAdapter.en.eq(1)
            yield
            # response should be ready, but until not read, making new request should be unavaliable
            assert (yield wbm.result.ready)
            assert not (yield wbm.request.ready)
            assert not (yield wbm.wbMaster.cyc)
            assert not (yield wbm.wbMaster.stb)
            # verify outut of result tranaction and if it was executed in the same clock cycle
            assert (yield resultAdapter.done)
            assert (yield resultAdapter.data_out.data) == 3
            yield resultAdapter.en.eq(0)
            yield
            # after fetching result only request method should be ready
            assert (yield wbm.request.ready)
            assert not (yield wbm.result.ready)
            yield
            # check if request is not repeated
            assert (yield wbm.request.ready)
            yield
            # make write req
            yield requestAdapter.data_in.addr.eq(3)
            yield requestAdapter.data_in.data.eq(4)
            yield requestAdapter.data_in.we.eq(1)
            yield requestAdapter.en.eq(1)
            yield
            assert (yield requestAdapter.done)
            yield requestAdapter.en.eq(0)
            yield
            assert not (yield wbm.request.ready)
            assert (yield wbm.wbMaster.dat_w) == 4
            # minimal 1-cycle delay
            # make rty response
            yield wbm.wbMaster.rty.eq(1)
            yield
            # expect restart of cycle
            yield wbm.wbMaster.rty.eq(0)
            yield
            assert (yield wbm.wbMaster.cyc)
            assert not (yield wbm.wbMaster.stb)
            assert not (yield wbm.request.ready)
            assert not (yield wbm.result.ready)
            yield
            assert (yield wbm.wbMaster.cyc)
            assert (yield wbm.wbMaster.stb)
            assert (yield wbm.wbMaster.dat_w) == 4
            # make err response
            yield wbm.wbMaster.err.eq(1)
            yield
            yield wbm.wbMaster.err.eq(0)
            yield
            assert (yield wbm.result.ready)
            yield resultAdapter.en.eq(1)
            yield
            assert (yield resultAdapter.done)
            assert (yield resultAdapter.data_out.err)
            assert not (yield wbm.request.ready)
            yield resultAdapter.en.eq(0)
            yield
            assert (yield wbm.request.ready)
            assert not (yield wbm.result.ready)
            assert not (yield wbm.wbMaster.cyc)
            assert not (yield wbm.wbMaster.stb)
            yield

        with self.runSimulation(twbm) as sim:
            sim.add_clock(1e-6)
            sim.add_sync_process(process)


class TestWishboneMuxer(TestCaseWithSimulator):
    def test_manual(self):
        wbRecord = Record(WishboneLayout(GenParams()).wb_layout)
        mux = WishboneMuxer(wbRecord, [Record.like(wbRecord, name=f"sl{i}") for i in range(2)], Signal(1))

        def process():
            yield mux.masterWb.cyc.eq(0)
            yield mux.masterWb.stb.eq(0)
            yield
            yield mux.masterWb.cyc.eq(1)
            yield mux.masterWb.stb.eq(1)
            yield mux.masterWb.we.eq(1)
            yield mux.sselTGA.eq(0)
            yield mux.masterWb.adr.eq(2)
            yield
            assert (yield mux.slaves[0].cyc)
            assert (yield mux.slaves[0].stb)
            assert not (yield mux.slaves[1].stb)
            assert (yield mux.slaves[0].we)
            yield mux.slaves[0].ack.eq(1)
            yield mux.slaves[0].dat_r.eq(4)
            yield mux.slaves[1].dat_r.eq(3)
            yield
            assert (yield mux.masterWb.ack)
            assert (yield mux.masterWb.dat_r) == 4
            yield mux.slaves[0].ack.eq(0)
            yield mux.masterWb.stb.eq(0)
            yield
            assert (yield mux.slaves[0].cyc)
            assert (yield mux.slaves[1].cyc)
            assert not (yield mux.slaves[0].stb)
            assert (yield mux.masterWb.dat_r) == 4
            yield mux.masterWb.stb.eq(1)
            yield mux.sselTGA.eq(1)
            yield
            assert not (yield mux.slaves[0].stb)
            assert (yield mux.slaves[1].stb)
            assert (yield mux.slaves[1].cyc)
            assert (yield mux.masterWb.dat_r) == 3
            yield mux.masterWb.cyc.eq(0)
            yield mux.masterWb.stb.eq(0)
            yield

        with self.runSimulation(mux) as sim:
            sim.add_clock(1e-6)
            sim.add_sync_process(process)


class TestWishboneAribiter(TestCaseWithSimulator):
    def test_manual(self):
        wbRecord = Record(WishboneLayout(GenParams()).wb_layout)
        arb = WishboneArbiter(wbRecord, [Record.like(wbRecord, name=f"mst{i}") for i in range(2)])

        def process():
            yield arb.masters[0].cyc.eq(0)
            yield arb.masters[0].stb.eq(0)
            yield arb.masters[1].cyc.eq(0)
            yield arb.masters[1].stb.eq(0)
            yield arb.masters[1].rst.eq(1)
            yield
            assert (yield arb.slaveWb.rst)
            assert not (yield wbRecord.cyc)
            yield arb.masters[0].cyc.eq(1)
            yield arb.masters[0].stb.eq(1)
            yield arb.masters[0].adr.eq(2)
            yield arb.masters[0].dat_w.eq(3)
            yield arb.masters[1].rst.eq(0)
            yield
            assert (yield wbRecord.dat_w) == 3
            assert (yield wbRecord.adr) == 2
            assert (yield wbRecord.cyc)
            assert (yield wbRecord.stb)
            yield arb.masters[1].cyc.eq(1)
            yield arb.masters[1].stb.eq(1)
            yield arb.masters[1].dat_w.eq(4)
            yield arb.slaveWb.ack.eq(1)
            yield
            assert (yield wbRecord.dat_w) == 3
            yield arb.masters[0].stb.eq(0)
            yield arb.slaveWb.ack.eq(0)
            yield
            assert not (yield wbRecord.stb)
            assert (yield wbRecord.cyc)
            assert (yield wbRecord.dat_w) == 3
            yield arb.masters[0].stb.eq(1)
            yield arb.masters[0].adr.eq(5)
            yield
            assert (yield wbRecord.dat_w) == 3
            assert (yield wbRecord.adr) == 5
            assert (yield wbRecord.cyc)
            assert (yield wbRecord.stb)
            yield arb.slaveWb.ack.eq(1)
            yield
            assert (yield arb.masters[0].ack)
            assert not (yield arb.masters[1].ack)
            yield arb.slaveWb.ack.eq(0)
            yield arb.masters[0].cyc.eq(0)
            yield arb.masters[0].stb.eq(0)
            yield
            assert not (yield wbRecord.cyc)
            assert not (yield wbRecord.stb)
            yield
            assert (yield wbRecord.cyc)
            assert (yield wbRecord.stb)
            assert (yield wbRecord.dat_w) == 4
            yield arb.slaveWb.ack.eq(1)
            yield
            assert not (yield arb.masters[0].ack)
            assert (yield arb.masters[1].ack)
            yield arb.slaveWb.ack.eq(0)
            yield arb.masters[1].stb.eq(0)
            yield arb.masters[1].cyc.eq(0)
            yield
            assert not (yield wbRecord.cyc)
            assert not (yield wbRecord.stb)
            yield
            yield
            yield arb.masters[0].cyc.eq(1)
            yield arb.masters[0].stb.eq(1)
            yield arb.masters[1].cyc.eq(1)
            yield arb.masters[1].stb.eq(1)
            yield
            yield
            assert (yield wbRecord.dat_w) == 3
            yield arb.masters[0].cyc.eq(0)
            yield arb.masters[0].stb.eq(0)
            yield arb.masters[1].cyc.eq(0)
            yield arb.masters[1].stb.eq(0)
            yield
            assert not (yield wbRecord.cyc)
            yield arb.masters[0].cyc.eq(1)
            yield arb.masters[0].stb.eq(1)
            yield arb.masters[1].cyc.eq(1)
            yield arb.masters[1].stb.eq(1)
            yield
            yield
            assert (yield wbRecord.dat_w) == 4

        with self.runSimulation(arb) as sim:
            sim.add_clock(1e-6)
            sim.add_sync_process(process)
