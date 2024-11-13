from collections.abc import Iterable
import random
from collections import deque

from amaranth.lib.wiring import connect
from amaranth_types import AnySimulatorContext, ValueLike

from coreblocks.peripherals.wishbone import *

from transactron.lib import AdapterTrans

from transactron.testing import *


class WishboneInterfaceWrapper:
    def __init__(self, wishbone_interface: WishboneInterface):
        self.wb = wishbone_interface

    def master_set(self, sim: AnySimulatorContext, addr: int, data: int, we: int):
        sim.set(self.wb.dat_w, data)
        sim.set(self.wb.adr, addr)
        sim.set(self.wb.we, we)
        sim.set(self.wb.cyc, 1)
        sim.set(self.wb.stb, 1)

    def master_release(self, sim: AnySimulatorContext, release_cyc: bool = True):
        sim.set(self.wb.stb, 0)
        if release_cyc:
            sim.set(self.wb.cyc, 0)

    async def slave_wait(self, sim: AnySimulatorContext):
        *_, adr, we, sel, dat_w = (
            await sim.tick()
            .sample(self.wb.adr, self.wb.we, self.wb.sel, self.wb.dat_w)
            .until(self.wb.stb & self.wb.cyc)
        )
        return adr, we, sel, dat_w

    async def slave_wait_and_verify(
        self, sim: AnySimulatorContext, exp_addr: int, exp_data: int, exp_we: int, exp_sel: int = 0
    ):
        adr, we, sel, dat_w = await self.slave_wait(sim)

        assert adr == exp_addr
        assert we == exp_we
        assert sel == exp_sel
        if exp_we:
            assert dat_w == exp_data

    async def slave_tick_and_verify(
        self, sim: AnySimulatorContext, exp_addr: int, exp_data: int, exp_we: int, exp_sel: int = 0
    ):
        *_, adr, we, sel, dat_w, stb, cyc = await sim.tick().sample(
            self.wb.adr, self.wb.we, self.wb.sel, self.wb.dat_w, self.wb.stb, self.wb.cyc
        )
        assert stb and cyc

        assert adr == exp_addr
        assert we == exp_we
        assert sel == exp_sel
        if exp_we:
            assert dat_w == exp_data

    async def slave_respond(
        self,
        sim: AnySimulatorContext,
        data: int,
        ack: int = 1,
        err: int = 0,
        rty: int = 0,
        sample: Iterable[ValueLike] = (),
    ):
        assert sim.get(self.wb.stb) and sim.get(self.wb.cyc)

        sim.set(self.wb.dat_r, data)
        sim.set(self.wb.ack, ack)
        sim.set(self.wb.err, err)
        sim.set(self.wb.rty, rty)
        ret = await sim.tick().sample(*sample)
        sim.set(self.wb.ack, 0)
        sim.set(self.wb.err, 0)
        sim.set(self.wb.rty, 0)
        return ret

    async def slave_respond_master_verify(
        self, sim: AnySimulatorContext, master: WishboneInterface, data: int, ack: int = 1, err: int = 0, rty: int = 0
    ):
        *_, ack, dat_r = await self.slave_respond(sim, data, ack, err, rty, sample=[master.ack, master.dat_r])
        assert ack and dat_r == data

    async def wait_ack(self, sim: AnySimulatorContext):
        await sim.tick().until(self.wb.stb & self.wb.cyc & self.wb.ack)


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

        async def process(sim: TestbenchContext):
            # read request
            await twbm.requestAdapter.call(sim, addr=2, data=0, we=0, sel=1)

            # read request after delay
            await sim.tick()
            await sim.tick()
            await twbm.requestAdapter.call(sim, addr=1, data=0, we=0, sel=1)

            # write request
            await twbm.requestAdapter.call(sim, addr=3, data=5, we=1, sel=0)

            # RTY and ERR responese
            await twbm.requestAdapter.call(sim, addr=2, data=0, we=0, sel=0)
            resp = await twbm.requestAdapter.call_try(sim, addr=0, data=0, we=0, sel=0)
            assert resp is None  # verify cycle restart

        async def result_process(sim: TestbenchContext):
            resp = await twbm.resultAdapter.call(sim)
            assert resp["data"] == 8
            assert not resp["err"]

            resp = await twbm.resultAdapter.call(sim)
            assert resp["data"] == 3
            assert not resp["err"]

            resp = await twbm.resultAdapter.call(sim)
            assert not resp["err"]

            resp = await twbm.resultAdapter.call(sim)
            assert resp["data"] == 1
            assert resp["err"]

        async def slave(sim: TestbenchContext):
            wwb = WishboneInterfaceWrapper(twbm.wbm.wb_master)

            await wwb.slave_wait_and_verify(sim, 2, 0, 0, 1)
            await wwb.slave_respond(sim, 8)

            await wwb.slave_wait_and_verify(sim, 1, 0, 0, 1)
            await wwb.slave_respond(sim, 3)

            await wwb.slave_tick_and_verify(sim, 3, 5, 1, 0)
            await wwb.slave_respond(sim, 0)
            await sim.tick()

            await wwb.slave_tick_and_verify(sim, 2, 0, 0, 0)
            await wwb.slave_respond(sim, 1, ack=0, err=0, rty=1)
            assert not sim.get(wwb.wb.stb)

            await wwb.slave_wait_and_verify(sim, 2, 0, 0, 0)
            await wwb.slave_respond(sim, 1, ack=1, err=1, rty=0)

        with self.run_simulation(twbm) as sim:
            sim.add_testbench(process)
            sim.add_testbench(result_process)
            sim.add_testbench(slave)


class TestWishboneMuxer(TestCaseWithSimulator):
    def test_manual(self):
        num_slaves = 4
        mux = WishboneMuxer(WishboneParameters(), num_slaves, Signal(num_slaves))
        slaves = [WishboneInterfaceWrapper(slave) for slave in mux.slaves]
        wb_master = WishboneInterfaceWrapper(mux.master_wb)

        async def process(sim: TestbenchContext):
            # check full communiaction
            wb_master.master_set(sim, 2, 0, 1)
            sim.set(mux.sselTGA, 0b0001)
            await slaves[0].slave_tick_and_verify(sim, 2, 0, 1)
            assert not sim.get(slaves[1].wb.stb)
            await slaves[0].slave_respond_master_verify(sim, wb_master.wb, 4)
            wb_master.master_release(sim, release_cyc=False)
            await sim.tick()
            # select without releasing cyc (only on stb)
            wb_master.master_set(sim, 3, 0, 0)
            sim.set(mux.sselTGA, 0b0010)
            await slaves[1].slave_tick_and_verify(sim, 3, 0, 0)
            assert not sim.get(slaves[0].wb.stb)
            await slaves[1].slave_respond_master_verify(sim, wb_master.wb, 5)
            wb_master.master_release(sim)
            await sim.tick()

            # normal selection
            wb_master.master_set(sim, 6, 0, 0)
            sim.set(mux.sselTGA, 0b1000)
            await slaves[3].slave_tick_and_verify(sim, 6, 0, 0)
            await slaves[3].slave_respond_master_verify(sim, wb_master.wb, 1)

        with self.run_simulation(mux) as sim:
            sim.add_testbench(process)


class TestWishboneArbiter(TestCaseWithSimulator):
    def test_manual(self):
        arb = WishboneArbiter(WishboneParameters(), 2)
        slave = WishboneInterfaceWrapper(arb.slave_wb)
        masters = [WishboneInterfaceWrapper(master) for master in arb.masters]

        async def process(sim: TestbenchContext):
            masters[0].master_set(sim, 2, 3, 1)
            await slave.slave_wait_and_verify(sim, 2, 3, 1)
            masters[1].master_set(sim, 1, 4, 1)
            await slave.slave_respond_master_verify(sim, masters[0].wb, 0)
            assert not sim.get(masters[1].wb.ack)
            masters[0].master_release(sim)
            await sim.tick()

            # check if bus is granted to next master if previous ends cycle
            await slave.slave_wait_and_verify(sim, 1, 4, 1)
            await slave.slave_respond_master_verify(sim, masters[1].wb, 0)
            assert not sim.get(masters[0].wb.ack)
            masters[1].master_release(sim)
            await sim.tick()

            # check round robin behaviour (2 masters requesting *2)
            masters[0].master_set(sim, 1, 0, 0)
            masters[1].master_set(sim, 2, 0, 0)
            await slave.slave_wait_and_verify(sim, 1, 0, 0)
            await slave.slave_respond_master_verify(sim, masters[0].wb, 3)
            masters[0].master_release(sim)
            masters[1].master_release(sim)
            await sim.tick()
            assert not sim.get(slave.wb.cyc)

            masters[0].master_set(sim, 1, 0, 0)
            masters[1].master_set(sim, 2, 0, 0)
            await slave.slave_wait_and_verify(sim, 2, 0, 0)
            await slave.slave_respond_master_verify(sim, masters[1].wb, 0)

            # check if releasing stb keeps grant
            masters[1].master_release(sim, release_cyc=False)
            await sim.tick()
            masters[1].master_set(sim, 3, 0, 0)
            await slave.slave_wait_and_verify(sim, 3, 0, 0)
            await slave.slave_respond_master_verify(sim, masters[1].wb, 0)

        with self.run_simulation(arb) as sim:
            sim.add_testbench(process)


class TestPipelinedWishboneMaster(TestCaseWithSimulator):
    def test_randomized(self):
        requests = 1000

        req_queue = deque()
        res_queue = deque()
        slave_queue = deque()

        random.seed(42)
        wb_params = WishboneParameters()
        pwbm = SimpleTestCircuit(PipelinedWishboneMaster((wb_params)))

        async def request_process(sim: TestbenchContext):
            for _ in range(requests):
                request = {
                    "addr": random.randint(0, 2**wb_params.addr_width - 1),
                    "data": random.randint(0, 2**wb_params.data_width - 1),
                    "we": random.randint(0, 1),
                    "sel": random.randint(0, 2**wb_params.granularity - 1),
                }
                req_queue.appendleft(request)
                await pwbm.request.call(sim, request)

        async def verify_process(sim: TestbenchContext):
            for _ in range(requests):
                await self.random_wait_geom(sim, 0.8)

                result = await pwbm.result.call(sim)
                cres = res_queue.pop()
                assert result["data"] == cres
                assert not result["err"]

        async def slave_process(sim: TestbenchContext):
            wbw = pwbm._dut.wb
            async for *_, cyc, stb, stall, adr, dat_w, we, sel in sim.tick().sample(
                wbw.cyc, wbw.stb, wbw.stall, wbw.adr, wbw.dat_w, wbw.we, wbw.sel
            ):
                if cyc and stb:
                    assert not stall
                    assert req_queue
                    c_req = req_queue.pop()
                    assert adr == c_req["addr"]
                    assert dat_w == c_req["data"]
                    assert we == c_req["we"]
                    assert sel == c_req["sel"]

                    slave_queue.appendleft(dat_w)
                    res_queue.appendleft(dat_w)

                if slave_queue and random.random() < 0.4:
                    sim.set(wbw.ack, 1)
                    sim.set(wbw.dat_r, slave_queue.pop())
                else:
                    sim.set(wbw.ack, 0)

                sim.set(wbw.stall, random.random() < 0.3)

        with self.run_simulation(pwbm) as sim:
            sim.add_testbench(request_process)
            sim.add_testbench(verify_process)
            sim.add_testbench(slave_process, background=True)


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
        self.m = WishboneMemorySlaveCircuit(wb_params=self.wb_params, mem_args={"depth": self.memsize, "init": []})

        self.sel_width = self.wb_params.data_width // self.wb_params.granularity

        random.seed(42)

    def test_randomized(self):
        req_queue = deque()

        mem_state = [0] * self.memsize

        async def request_process(sim: TestbenchContext):
            for _ in range(self.iters):
                req = {
                    "addr": random.randint(0, self.memsize - 1),
                    "data": random.randint(0, 2**self.wb_params.data_width - 1),
                    "we": random.randint(0, 1),
                    "sel": random.randint(0, 2**self.sel_width - 1),
                }
                req_queue.appendleft(req)

                await self.random_wait_geom(sim, 0.2)
                await self.m.request.call(sim, req)

        async def result_process(sim: TestbenchContext):
            for _ in range(self.iters):
                await self.random_wait_geom(sim, 0.2)
                res = await self.m.result.call(sim)
                req = req_queue.pop()

                if not req["we"]:
                    assert res["data"] == mem_state[req["addr"]]
                else:
                    for i in range(self.sel_width):
                        if req["sel"] & (1 << i):
                            granularity_mask = (2**self.wb_params.granularity - 1) << (i * self.wb_params.granularity)
                            mem_state[req["addr"]] &= ~granularity_mask
                            mem_state[req["addr"]] |= req["data"] & granularity_mask
                    val = sim.get(Value.cast(self.m.mem_slave.mem.data[req["addr"]]))
                    assert val == mem_state[req["addr"]]

        with self.run_simulation(self.m, max_cycles=3000) as sim:
            sim.add_testbench(request_process)
            sim.add_testbench(result_process)
