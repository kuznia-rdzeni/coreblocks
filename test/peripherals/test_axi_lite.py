from transactron.utils import ModuleConnector
from coreblocks.peripherals.axi_lite import *
from transactron import Method, def_method, TModule
from transactron.lib import AdapterTrans

from transactron.testing import *


class AXILiteInterfaceWrapper:
    def __init__(self, axi_lite_master: AXILiteInterface):
        self.axi_lite = axi_lite_master

    def slave_ra_ready(self, sim: TestbenchContext, rdy=1):
        sim.set(self.axi_lite.read_address.rdy, rdy)

    def slave_ra_get(self, sim: TestbenchContext):
        ra = self.axi_lite.read_address
        assert sim.get(ra.valid)
        return sim.get(ra.addr), sim.get(ra.prot)

    def slave_ra_get_and_verify(self, sim: TestbenchContext, exp_addr: int, exp_prot: int):
        addr, prot = self.slave_ra_get(sim)
        assert addr == exp_addr
        assert prot == exp_prot

    async def slave_rd_wait(self, sim: TestbenchContext):
        rd = self.axi_lite.read_data
        while not sim.get(rd.rdy):
            await sim.tick()

    def slave_rd_get(self, sim: TestbenchContext):
        rd = self.axi_lite.read_data
        assert sim.get(rd.rdy)

    async def slave_rd_respond(self, sim: TestbenchContext, data, resp=0):
        assert sim.get(self.axi_lite.read_data.rdy)
        sim.set(self.axi_lite.read_data.data, data)
        sim.set(self.axi_lite.read_data.resp, resp)
        sim.set(self.axi_lite.read_data.valid, 1)
        await sim.tick()
        sim.set(self.axi_lite.read_data.valid, 0)

    def slave_wa_ready(self, sim: TestbenchContext, rdy=1):
        sim.set(self.axi_lite.write_address.rdy, rdy)

    def slave_wa_get(self, sim: TestbenchContext):
        wa = self.axi_lite.write_address
        assert sim.get(wa.valid)
        return sim.get(wa.addr), sim.get(wa.prot)

    def slave_wa_get_and_verify(self, sim: TestbenchContext, exp_addr, exp_prot):
        addr, prot = self.slave_wa_get(sim)
        assert addr == exp_addr
        assert prot == exp_prot

    def slave_wd_ready(self, sim: TestbenchContext, rdy=1):
        sim.set(self.axi_lite.write_data.rdy, rdy)

    def slave_wd_get(self, sim: TestbenchContext):
        wd = self.axi_lite.write_data
        assert sim.get(wd.valid)
        return sim.get(wd.data), sim.get(wd.strb)

    def slave_wd_get_and_verify(self, sim: TestbenchContext, exp_data, exp_strb):
        data, strb = self.slave_wd_get(sim)
        assert data == exp_data
        assert strb == exp_strb

    def slave_wr_get(self, sim: TestbenchContext):
        wr = self.axi_lite.write_response
        assert sim.get(wr.rdy)

    async def slave_wr_respond(self, sim: TestbenchContext, resp=0):
        assert sim.get(self.axi_lite.write_response.rdy)
        sim.set(self.axi_lite.write_response.resp, resp)
        sim.set(self.axi_lite.write_response.valid, 1)
        await sim.tick()
        sim.set(self.axi_lite.write_response.valid, 0)


# TODO: this test needs a rewrite!
# 1. use queues instead of copy-pasting
# 2. handle each AXI pipe independently
class TestAXILiteMaster(TestCaseWithSimulator):
    def test_manual(self):
        alm = AXILiteMaster(AXILiteParameters())
        almt = SimpleTestCircuit(alm)

        m = TModule()
        write_request = Method(
            i=[
                ("addr", alm.axil_params.addr_width),
                ("prot", 3),
                ("data", alm.axil_params.data_width),
                ("strb", alm.axil_params.data_width // 8),
            ]
        )

        @def_method(m, write_request, ready=alm.wa_request.ready & alm.wd_request.ready)
        def _(arg):
            alm.wa_request(m, addr=arg.addr, prot=arg.prot)
            alm.wd_request(m, data=arg.data, strb=arg.strb)

        write_request_adapter = TestbenchIO(AdapterTrans.create(write_request))

        dut = ModuleConnector(m, write_request_adapter, axi_lite_master=almt)

        async def master_process(sim: TestbenchContext):
            # read request
            await almt.ra_request.call(sim, addr=5, prot=0)

            await almt.ra_request.call(sim, addr=10, prot=1)

            await almt.ra_request.call(sim, addr=15, prot=1)

            await almt.ra_request.call(sim, addr=20, prot=0)

            await write_request_adapter.call(sim, addr=6, prot=0, data=10, strb=3)

            await write_request_adapter.call(sim, addr=7, prot=0, data=11, strb=3)

            await write_request_adapter.call(sim, addr=8, prot=0, data=12, strb=3)

            await write_request_adapter.call(sim, addr=9, prot=1, data=13, strb=4)

            await almt.ra_request.call(sim, addr=1, prot=1)

            await almt.ra_request.call(sim, addr=2, prot=1)

        async def slave_process(sim: TestbenchContext):
            slave = AXILiteInterfaceWrapper(alm.axil_master)

            # 1st request
            slave.slave_ra_ready(sim, 1)
            await sim.tick()
            slave.slave_ra_get_and_verify(sim, 5, 0)

            # 2nd request and 1st respond
            await sim.tick()
            slave.slave_ra_get_and_verify(sim, 10, 1)
            slave.slave_rd_get(sim)
            await slave.slave_rd_respond(sim, 10, 0)

            # 3rd request and 2nd respond
            slave.slave_ra_get_and_verify(sim, 15, 1)
            slave.slave_rd_get(sim)
            await slave.slave_rd_respond(sim, 15, 0)

            # 4th request and 3rd respond
            slave.slave_ra_get_and_verify(sim, 20, 0)
            slave.slave_rd_get(sim)
            await slave.slave_rd_respond(sim, 20, 0)

            # 4th respond and 1st write request
            slave.slave_ra_ready(sim, 0)
            slave.slave_wa_ready(sim, 1)
            slave.slave_wd_ready(sim, 1)
            slave.slave_rd_get(sim)
            slave.slave_wa_get_and_verify(sim, 6, 0)
            slave.slave_wd_get_and_verify(sim, 10, 3)
            await slave.slave_rd_respond(sim, 25, 0)

            # 2nd write request and 1st respond
            slave.slave_wa_get_and_verify(sim, 7, 0)
            slave.slave_wd_get_and_verify(sim, 11, 3)
            slave.slave_wr_get(sim)
            await slave.slave_wr_respond(sim, 1)

            # 3rd write request and 2nd respond
            slave.slave_wa_get_and_verify(sim, 8, 0)
            slave.slave_wd_get_and_verify(sim, 12, 3)
            slave.slave_wr_get(sim)
            await slave.slave_wr_respond(sim, 1)

            # 4th write request and 3rd respond
            slave.slave_wa_get_and_verify(sim, 9, 1)
            slave.slave_wd_get_and_verify(sim, 13, 4)
            slave.slave_wr_get(sim)
            await slave.slave_wr_respond(sim, 1)

            # 4th respond
            slave.slave_wa_ready(sim, 0)
            slave.slave_wd_ready(sim, 0)
            slave.slave_wr_get(sim)
            await slave.slave_wr_respond(sim, 0)

            slave.slave_ra_get(sim)
            await self.tick(sim, 2)
            slave.slave_ra_ready(sim, 1)
            slave.slave_ra_get_and_verify(sim, 1, 1)
            # wait for next rising edge
            await sim.tick()

            slave.slave_ra_get(sim)
            slave.slave_ra_get_and_verify(sim, 2, 1)
            slave.slave_rd_get(sim)
            await slave.slave_rd_respond(sim, 3, 1)

            await slave.slave_rd_wait(sim)
            await slave.slave_rd_respond(sim, 4, 1)

        async def result_process(sim: TestbenchContext):
            resp = await almt.rd_response.call(sim)
            assert resp["data"] == 10
            assert resp["resp"] == 0

            resp = await almt.rd_response.call(sim)
            assert resp["data"] == 15
            assert resp["resp"] == 0

            resp = await almt.rd_response.call(sim)
            assert resp["data"] == 20
            assert resp["resp"] == 0

            resp = await almt.rd_response.call(sim)
            assert resp["data"] == 25
            assert resp["resp"] == 0

            resp = await almt.wr_response.call(sim)
            assert resp["resp"] == 1

            resp = await almt.wr_response.call(sim)
            assert resp["resp"] == 1

            resp = await almt.wr_response.call(sim)
            assert resp["resp"] == 1

            resp = await almt.wr_response.call(sim)
            assert resp["resp"] == 0

            for _ in range(5):
                await sim.tick()

            resp = await almt.rd_response.call(sim)
            assert resp["data"] == 3
            assert resp["resp"] == 1

            resp = await almt.rd_response.call(sim)
            assert resp["data"] == 4
            assert resp["resp"] == 1

        with self.run_simulation(dut) as sim:
            sim.add_testbench(master_process)
            sim.add_testbench(slave_process)
            sim.add_testbench(result_process)
