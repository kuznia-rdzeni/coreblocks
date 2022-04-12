# Testbench for WishboneMaster, WishboneMuxer and WishboneArbiter

from coreblocks.wishbone import *
from amaranth.sim import Simulator

wbm = WishboneMaster()
def wbm_bench():
    yield
    # reset cycle
    assert (yield wbm.wbMaster.rst)
    yield
    assert not (yield wbm.wbMaster.cyc)
    assert not (yield wbm.wbMaster.stb)
    yield
    # request read
    yield wbm.cpuCon.addr.eq(2)
    yield wbm.cpuCon.we.eq(0)
    yield wbm.cpuCon.request.eq(1)
    yield
    # check latching
    yield wbm.cpuCon.addr.eq(1)
    yield
    assert (yield wbm.cpuCon.busy)
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
    assert (yield wbm.cpuCon.busy)
    assert not (yield wbm.cpuCon.done)
    yield wbm.wbMaster.ack.eq(0)
    # check cpu response and wb cycle end
    yield
    assert not (yield wbm.cpuCon.busy)
    assert (yield wbm.cpuCon.done)
    assert (yield wbm.cpuCon.data_o) == 3
    assert not (yield wbm.wbMaster.cyc)
    assert not (yield wbm.wbMaster.stb)
    yield
    # check if request is latched only on edge
    assert not (yield wbm.cpuCon.busy)
    yield wbm.cpuCon.request.eq(0)
    yield
    # make write req
    yield wbm.cpuCon.addr.eq(3)
    yield wbm.cpuCon.we.eq(1)
    yield wbm.cpuCon.data.eq(4)
    yield wbm.cpuCon.request.eq(1)
    yield
    yield wbm.cpuCon.data.eq(3)
    yield
    assert (yield wbm.cpuCon.busy)
    # minimal cycle delay
    assert (yield wbm.wbMaster.dat_w) == 4
    # make rty response
    yield wbm.wbMaster.rty.eq(1)
    yield
    # expect restart of cycle
    yield wbm.wbMaster.rty.eq(0)
    yield
    assert (yield wbm.wbMaster.cyc)
    assert not (yield wbm.wbMaster.stb)
    assert (yield wbm.cpuCon.busy)
    yield
    assert (yield wbm.wbMaster.cyc)
    assert (yield wbm.wbMaster.stb)
    assert (yield wbm.wbMaster.dat_w) == 4
    # make err response
    yield wbm.wbMaster.err.eq(1)
    yield
    yield wbm.wbMaster.err.eq(0)
    yield
    assert not (yield wbm.cpuCon.busy)
    assert (yield wbm.cpuCon.done)
    assert (yield wbm.cpuCon.err)
    assert not (yield wbm.wbMaster.cyc)
    assert not (yield wbm.wbMaster.stb)
    yield
    assert not (yield wbm.cpuCon.err)
    yield

sim = Simulator(wbm)
sim.add_clock(1e-6)
sim.add_sync_process(wbm_bench)
with sim.write_vcd("wishbone_master.vcd"):
    sim.run()
    print("WishboneMaster test passed")

mux = WishboneMuxer(Record.like(wbRecord, name="mst"), 
    [Record.like(wbRecord, name=f"sl{i}") for i in range(2)], Signal(1))
def mux_bench():
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

sim = Simulator(mux)
sim.add_clock(1e-6)
sim.add_sync_process(mux_bench)
with sim.write_vcd("wishbone_muxer.vcd"):
    sim.run()
    print("WishboneMuxer test passed")

arb = WishboneArbiter(wbRecord, [Record.like(wbRecord, name=f"mst{i}") for i in range(2)])
def arb_bench():
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


sim = Simulator(arb)
sim.add_clock(1e-6)
sim.add_sync_process(arb_bench)
with sim.write_vcd("wishbone_arbiter.vcd"):
    sim.run() 
    print("WishboneArbiter test passed")
