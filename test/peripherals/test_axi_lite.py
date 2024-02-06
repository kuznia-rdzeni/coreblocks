from coreblocks.peripherals.axi_lite import *
from transactron import Method, def_method, TModule
from transactron.lib import AdapterTrans

from transactron.testing import *


class AXILiteInterfaceWrapper:
    def __init__(self, axi_lite_master: Record):
        self.axi_lite = axi_lite_master

    def slave_ra_ready(self, rdy=1):
        yield self.axi_lite.read_address.rdy.eq(rdy)

    def slave_ra_wait(self):
        while not (yield self.axi_lite.read_address.valid):
            yield

    def slave_ra_verify(self, exp_addr, prot):
        assert (yield self.axi_lite.read_address.valid)
        assert (yield self.axi_lite.read_address.addr) == exp_addr
        assert (yield self.axi_lite.read_address.prot) == prot

    def slave_rd_wait(self):
        while not (yield self.axi_lite.read_data.rdy):
            yield

    def slave_rd_respond(self, data, resp=0):
        assert (yield self.axi_lite.read_data.rdy)
        yield self.axi_lite.read_data.data.eq(data)
        yield self.axi_lite.read_data.resp.eq(resp)
        yield self.axi_lite.read_data.valid.eq(1)
        yield
        yield self.axi_lite.read_data.valid.eq(0)

    def slave_wa_ready(self, rdy=1):
        yield self.axi_lite.write_address.rdy.eq(rdy)

    def slave_wa_wait(self):
        while not (yield self.axi_lite.write_address.valid):
            yield

    def slave_wa_verify(self, exp_addr, prot):
        assert (yield self.axi_lite.write_address.valid)
        assert (yield self.axi_lite.write_address.addr) == exp_addr
        assert (yield self.axi_lite.write_address.prot) == prot

    def slave_wd_ready(self, rdy=1):
        yield self.axi_lite.write_data.rdy.eq(rdy)

    def slave_wd_wait(self):
        while not (yield self.axi_lite.write_data.valid):
            yield

    def slave_wd_verify(self, exp_data, strb):
        assert (yield self.axi_lite.write_data.valid)
        assert (yield self.axi_lite.write_data.data) == exp_data
        assert (yield self.axi_lite.write_data.strb) == strb

    def slave_wr_wait(self):
        while not (yield self.axi_lite.write_response.rdy):
            yield

    def slave_wr_respond(self, resp=0):
        assert (yield self.axi_lite.write_response.rdy)
        yield self.axi_lite.write_response.resp.eq(resp)
        yield self.axi_lite.write_response.valid.eq(1)
        yield
        yield self.axi_lite.write_response.valid.eq(0)


class TestAXILiteMaster(TestCaseWithSimulator):
    class AXILiteMasterTestModule(Elaboratable):
        def __init__(self, params: AXILiteParameters):
            self.params = params
            self.write_request_layout = [
                ("addr", self.params.addr_width),
                ("prot", 3),
                ("data", self.params.data_width),
                ("strb", self.params.data_width // 8),
            ]

            self.write_request = Method(i=self.write_request_layout)

        def elaborate(self, platform):
            m = TModule()
            m.submodules.alm = alm = self.axi_lite_master = AXILiteMaster(self.params)
            m.submodules.rar = self.read_address_request_adapter = TestbenchIO(AdapterTrans(alm.ra_request))
            m.submodules.rdr = self.read_data_response_adapter = TestbenchIO(AdapterTrans(alm.rd_response))
            m.submodules.war = self.write_address_request_adapter = TestbenchIO(AdapterTrans(alm.wa_request))
            m.submodules.wdr = self.write_data_request_adapter = TestbenchIO(AdapterTrans(alm.wd_request))
            m.submodules.wrr = self.write_response_response_adapter = TestbenchIO(AdapterTrans(alm.wr_response))

            @def_method(m, self.write_request, ready=alm.wa_request.ready & alm.wd_request.ready)
            def _(arg):
                alm.wa_request(m, addr=arg.addr, prot=arg.prot)
                alm.wd_request(m, data=arg.data, strb=arg.strb)

            m.submodules.wr = self.write_request_adapter = TestbenchIO(AdapterTrans(self.write_request))

            return m

    def test_manual(self):
        almt = TestAXILiteMaster.AXILiteMasterTestModule(AXILiteParameters())

        def master_process():
            # read request
            yield from almt.read_address_request_adapter.call(addr=5, prot=0)

            yield from almt.read_address_request_adapter.call(addr=10, prot=1)

            yield from almt.read_address_request_adapter.call(addr=15, prot=1)

            yield from almt.read_address_request_adapter.call(addr=20, prot=0)

            yield from almt.write_request_adapter.call(addr=6, prot=0, data=10, strb=3)

            yield from almt.write_request_adapter.call(addr=7, prot=0, data=11, strb=3)

            yield from almt.write_request_adapter.call(addr=8, prot=0, data=12, strb=3)

            yield from almt.write_request_adapter.call(addr=9, prot=1, data=13, strb=4)

            yield from almt.read_address_request_adapter.call(addr=1, prot=1)

            yield from almt.read_address_request_adapter.call(addr=2, prot=1)

        def slave_process():
            slave = AXILiteInterfaceWrapper(almt.axi_lite_master.axil_master)

            # 1st request
            yield from slave.slave_ra_ready(1)
            yield from slave.slave_ra_wait()
            yield from slave.slave_ra_verify(5, 0)
            yield Settle()

            # 2nd request and 1st respond
            yield from slave.slave_ra_wait()
            yield from slave.slave_rd_wait()
            yield from slave.slave_ra_verify(10, 1)
            yield from slave.slave_rd_respond(10, 0)
            yield Settle()

            # 3rd request and 2nd respond
            yield from slave.slave_ra_wait()
            yield from slave.slave_rd_wait()
            yield from slave.slave_ra_verify(15, 1)
            yield from slave.slave_rd_respond(15, 0)
            yield Settle()

            # 4th request and 3rd respond
            yield from slave.slave_ra_wait()
            yield from slave.slave_rd_wait()
            yield from slave.slave_ra_verify(20, 0)
            yield from slave.slave_rd_respond(20, 0)
            yield Settle()

            # 4th respond and 1st write request
            yield from slave.slave_ra_ready(0)
            yield from slave.slave_wa_ready(1)
            yield from slave.slave_wd_ready(1)
            yield from slave.slave_rd_wait()
            yield from slave.slave_wa_wait()
            yield from slave.slave_wd_wait()
            yield from slave.slave_wa_verify(6, 0)
            yield from slave.slave_wd_verify(10, 3)
            yield from slave.slave_rd_respond(25, 0)
            yield Settle()

            # 2nd write request and 1st respond
            yield from slave.slave_wa_wait()
            yield from slave.slave_wd_wait()
            yield from slave.slave_wr_wait()
            yield from slave.slave_wa_verify(7, 0)
            yield from slave.slave_wd_verify(11, 3)
            yield from slave.slave_wr_respond(1)
            yield Settle()

            # 3nd write request and 2st respond
            yield from slave.slave_wa_wait()
            yield from slave.slave_wd_wait()
            yield from slave.slave_wr_wait()
            yield from slave.slave_wa_verify(8, 0)
            yield from slave.slave_wd_verify(12, 3)
            yield from slave.slave_wr_respond(1)
            yield Settle()

            # 4th write request and 3rd respond
            yield from slave.slave_wr_wait()
            yield from slave.slave_wa_verify(9, 1)
            yield from slave.slave_wd_verify(13, 4)
            yield from slave.slave_wr_respond(1)
            yield Settle()

            # 4th respond
            yield from slave.slave_wa_ready(0)
            yield from slave.slave_wd_ready(0)
            yield from slave.slave_wr_wait()
            yield from slave.slave_wr_respond(0)
            yield Settle()

            yield from slave.slave_ra_wait()
            for _ in range(2):
                yield
            yield from slave.slave_ra_ready(1)
            yield from slave.slave_ra_verify(1, 1)
            # wait for next rising edge
            yield
            yield

            yield from slave.slave_ra_wait()
            yield from slave.slave_ra_verify(2, 1)
            yield from slave.slave_rd_wait()
            yield from slave.slave_rd_respond(3, 1)
            yield Settle()

            yield from slave.slave_rd_wait()
            yield from slave.slave_rd_respond(4, 1)

        def result_process():
            resp = yield from almt.read_data_response_adapter.call()
            self.assertEqual(resp["data"], 10)
            self.assertEqual(resp["resp"], 0)

            resp = yield from almt.read_data_response_adapter.call()
            self.assertEqual(resp["data"], 15)
            self.assertEqual(resp["resp"], 0)

            resp = yield from almt.read_data_response_adapter.call()
            self.assertEqual(resp["data"], 20)
            self.assertEqual(resp["resp"], 0)

            resp = yield from almt.read_data_response_adapter.call()
            self.assertEqual(resp["data"], 25)
            self.assertEqual(resp["resp"], 0)

            resp = yield from almt.write_response_response_adapter.call()
            self.assertEqual(resp["resp"], 1)

            resp = yield from almt.write_response_response_adapter.call()
            self.assertEqual(resp["resp"], 1)

            resp = yield from almt.write_response_response_adapter.call()
            self.assertEqual(resp["resp"], 1)

            resp = yield from almt.write_response_response_adapter.call()
            self.assertEqual(resp["resp"], 0)

            for _ in range(5):
                yield

            resp = yield from almt.read_data_response_adapter.call()
            self.assertEqual(resp["data"], 3)
            self.assertEqual(resp["resp"], 1)

            resp = yield from almt.read_data_response_adapter.call()
            self.assertEqual(resp["data"], 4)
            self.assertEqual(resp["resp"], 1)

        with self.run_simulation(almt) as sim:
            sim.add_sync_process(master_process)
            sim.add_sync_process(slave_process)
            sim.add_sync_process(result_process)
