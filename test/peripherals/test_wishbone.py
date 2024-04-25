import random
from collections import deque

from amaranth.lib.wiring import connect

from coreblocks.peripherals.wishbone import *

from transactron.lib import AdapterTrans

from transactron.testing import *


class WishboneInterfaceWrapper:
    def __init__(self, wishbone_interface: WishboneInterface):
        self.wb = wishbone_interface

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
        assert (yield self.wb.we) == exp_we
        assert (yield self.wb.sel) == exp_sel
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

    def wait_ack(self):
        while not ((yield self.wb.stb) and (yield self.wb.cyc) and (yield self.wb.ack)):
            yield


class TestWishboneMaster(TestCaseWithSimulator):
    class WishboneMasterTestModule(Elaboratable):
        def __init__(self):
            pass

        def elaborate(self, platform):
            m = Module()
            m.submodules.wbm = self.wbm = wbm = WishboneMaster(WishboneParameters())
            m.submodules.rqa = self.requestAdapter = TestbenchIO(AdapterTrans(wbm.request))
            m.submodules.rsa = self.resultAdapter = TestbenchIO(AdapterTrans(wbm.result))
            return m

    def test_manual(self):
        twbm = TestWishboneMaster.WishboneMasterTestModule()

        def process():
            # read request
            yield from twbm.requestAdapter.call(addr=2, data=0, we=0, sel=1)

            # read request after delay
            yield
            yield
            yield from twbm.requestAdapter.call(addr=1, data=0, we=0, sel=1)

            # write request
            yield from twbm.requestAdapter.call(addr=3, data=5, we=1, sel=0)

            # RTY and ERR responese
            yield from twbm.requestAdapter.call(addr=2, data=0, we=0, sel=0)
            resp = yield from twbm.requestAdapter.call_try(addr=0, data=0, we=0, sel=0)
            assert resp is None  # verify cycle restart

        def result_process():
            resp = yield from twbm.resultAdapter.call()
            assert resp["data"] == 8
            assert not resp["err"]

            resp = yield from twbm.resultAdapter.call()
            assert resp["data"] == 3
            assert not resp["err"]

            resp = yield from twbm.resultAdapter.call()
            assert not resp["err"]

            resp = yield from twbm.resultAdapter.call()
            assert resp["data"] == 1
            assert resp["err"]

        def slave():
            wwb = WishboneInterfaceWrapper(twbm.wbm.wb_master)

            yield from wwb.slave_wait()
            yield from wwb.slave_verify(2, 0, 0, 1)
            yield from wwb.slave_respond(8)
            yield Settle()

            yield from wwb.slave_wait()
            yield from wwb.slave_verify(1, 0, 0, 1)
            yield from wwb.slave_respond(3)
            yield Settle()

            yield  # consecutive request
            yield from wwb.slave_verify(3, 5, 1, 0)
            yield from wwb.slave_respond(0)
            yield

            yield  # consecutive request
            yield from wwb.slave_verify(2, 0, 0, 0)
            yield from wwb.slave_respond(1, ack=0, err=0, rty=1)
            yield Settle()
            assert not (yield wwb.wb.stb)

            yield from wwb.slave_wait()
            yield from wwb.slave_verify(2, 0, 0, 0)
            yield from wwb.slave_respond(1, ack=1, err=1, rty=0)

        with self.run_simulation(twbm) as sim:
            sim.add_sync_process(process)
            sim.add_sync_process(result_process)
            sim.add_sync_process(slave)


class TestWishboneMuxer(TestCaseWithSimulator):
    def test_manual(self):
        num_slaves = 4
        mux = WishboneMuxer(WishboneParameters(), num_slaves, Signal(num_slaves))
        slaves = [WishboneInterfaceWrapper(slave) for slave in mux.slaves]
        wb_master = WishboneInterfaceWrapper(mux.master_wb)

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

        with self.run_simulation(mux) as sim:
            sim.add_sync_process(process)


class TestWishboneAribiter(TestCaseWithSimulator):
    def test_manual(self):
        arb = WishboneArbiter(WishboneParameters(), 2)
        slave = WishboneInterfaceWrapper(arb.slave_wb)
        masters = [WishboneInterfaceWrapper(master) for master in arb.masters]

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

        with self.run_simulation(arb) as sim:
            sim.add_sync_process(process)


class TestPipelinedWishboneMaster(TestCaseWithSimulator):
    def test_randomized(self):
        requests = 1000

        req_queue = deque()
        res_queue = deque()
        slave_queue = deque()

        random.seed(42)
        wb_params = WishboneParameters()
        pwbm = SimpleTestCircuit(PipelinedWishboneMaster((wb_params)))

        def request_process():
            for _ in range(requests):
                request = {
                    "addr": random.randint(0, 2**wb_params.addr_width - 1),
                    "data": random.randint(0, 2**wb_params.data_width - 1),
                    "we": random.randint(0, 1),
                    "sel": random.randint(0, 2**wb_params.granularity - 1),
                }
                req_queue.appendleft(request)
                yield from pwbm.request.call(request)

        def verify_process():
            for _ in range(requests):
                while random.random() < 0.8:
                    yield

                result = yield from pwbm.result.call()
                cres = res_queue.pop()
                assert result["data"] == cres
                assert not result["err"]

        def slave_process():
            yield Passive()

            wbw = pwbm._dut.wb
            while True:
                if (yield wbw.cyc) and (yield wbw.stb):
                    assert not (yield wbw.stall)
                    assert req_queue
                    c_req = req_queue.pop()
                    assert (yield wbw.adr) == c_req["addr"]
                    assert (yield wbw.dat_w) == c_req["data"]
                    assert (yield wbw.we) == c_req["we"]
                    assert (yield wbw.sel) == c_req["sel"]

                    slave_queue.appendleft((yield wbw.dat_w))
                    res_queue.appendleft((yield wbw.dat_w))

                if slave_queue and random.random() < 0.4:
                    yield wbw.ack.eq(1)
                    yield wbw.dat_r.eq(slave_queue.pop())
                else:
                    yield wbw.ack.eq(0)

                yield wbw.stall.eq(random.random() < 0.3)

                yield

        with self.run_simulation(pwbm) as sim:
            sim.add_sync_process(request_process)
            sim.add_sync_process(verify_process)
            sim.add_sync_process(slave_process)


class WishboneMemorySlaveCircuit(Elaboratable):
    def __init__(self, wb_params: WishboneParameters, mem_args: dict):
        self.wb_params = wb_params
        self.mem_args = mem_args

    def elaborate(self, platform):
        m = Module()

        m.submodules.mem_slave = self.mem_slave = WishboneMemorySlave(self.wb_params, **self.mem_args)
        m.submodules.mem_master = self.mem_master = WishboneMaster(self.wb_params)
        m.submodules.request = self.request = TestbenchIO(AdapterTrans(self.mem_master.request))
        m.submodules.result = self.result = TestbenchIO(AdapterTrans(self.mem_master.result))

        connect(m, self.mem_master.wb_master, self.mem_slave.bus)

        return m


class TestWishboneMemorySlave(TestCaseWithSimulator):
    def setup_method(self):
        self.memsize = 43  # test some weird depth
        self.iters = 300

        self.addr_width = (self.memsize - 1).bit_length()  # nearest log2 >= log2(memsize)
        self.wb_params = WishboneParameters(data_width=32, addr_width=self.addr_width, granularity=16)
        self.m = WishboneMemorySlaveCircuit(wb_params=self.wb_params, mem_args={"depth": self.memsize})

        self.sel_width = self.wb_params.data_width // self.wb_params.granularity

        random.seed(42)

    def test_randomized(self):
        req_queue = deque()
        wr_queue = deque()

        mem_state = [0] * self.memsize

        def request_process():
            for _ in range(self.iters):
                req = {
                    "addr": random.randint(0, self.memsize - 1),
                    "data": random.randint(0, 2**self.wb_params.data_width - 1),
                    "we": random.randint(0, 1),
                    "sel": random.randint(0, 2**self.sel_width - 1),
                }
                req_queue.appendleft(req)
                wr_queue.appendleft(req)

                while random.random() < 0.2:
                    yield
                yield from self.m.request.call(req)

        def result_process():
            for _ in range(self.iters):
                while random.random() < 0.2:
                    yield
                res = yield from self.m.result.call()
                req = req_queue.pop()

                if not req["we"]:
                    assert res["data"] == mem_state[req["addr"]]

        def write_process():
            wwb = WishboneInterfaceWrapper(self.m.mem_master.wb_master)
            for _ in range(self.iters):
                yield from wwb.wait_ack()
                req = wr_queue.pop()

                if req["we"]:
                    for i in range(self.sel_width):
                        if req["sel"] & (1 << i):
                            granularity_mask = (2**self.wb_params.granularity - 1) << (i * self.wb_params.granularity)
                            mem_state[req["addr"]] &= ~granularity_mask
                            mem_state[req["addr"]] |= req["data"] & granularity_mask

                yield

                if req["we"]:
                    assert (yield self.m.mem_slave.mem[req["addr"]]) == mem_state[req["addr"]]

        with self.run_simulation(self.m, max_cycles=3000) as sim:
            sim.add_sync_process(request_process)
            sim.add_sync_process(result_process)
            sim.add_sync_process(write_process)
