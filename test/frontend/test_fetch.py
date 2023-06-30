from collections import deque

import random

from amaranth import Elaboratable, Module
from amaranth.sim import Passive

from coreblocks.transactions.core import Method
from coreblocks.transactions.lib import AdapterTrans, FIFO, Adapter
from coreblocks.frontend.fetch import Fetch
from coreblocks.frontend.icache import ICacheInterface
from coreblocks.params import GenParams, FetchLayouts, ICacheLayouts
from coreblocks.params.configurations import test_core_config
from ..common import TestCaseWithSimulator, TestbenchIO, def_method_mock


class MockedICache(Elaboratable, ICacheInterface):
    def __init__(self, gen_params: GenParams):
        layouts = gen_params.get(ICacheLayouts)

        self.issue_req_io = TestbenchIO(Adapter(i=layouts.issue_req))
        self.accept_res_io = TestbenchIO(Adapter(o=layouts.accept_res))

        self.issue_req = self.issue_req_io.adapter.iface
        self.accept_res = self.accept_res_io.adapter.iface
        self.flush = Method()

    def elaborate(self, platform):
        m = Module()

        m.submodules.issue_req_io = self.issue_req_io
        m.submodules.accept_res_io = self.accept_res_io

        return m


class TestElaboratable(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.gp = gen_params

    def elaborate(self, platform):
        m = Module()

        self.icache = MockedICache(self.gp)

        fifo = FIFO(self.gp.get(FetchLayouts).raw_instr, depth=2)
        self.io_out = TestbenchIO(AdapterTrans(fifo.read))
        self.fetch = Fetch(self.gp, self.icache, fifo.write)
        self.verify_branch = TestbenchIO(AdapterTrans(self.fetch.verify_branch))

        m.submodules.icache = self.icache
        m.submodules.fetch = self.fetch
        m.submodules.io_out = self.io_out
        m.submodules.verify_branch = self.verify_branch
        m.submodules.fifo = fifo

        return m


class TestFetch(TestCaseWithSimulator):
    def setUp(self) -> None:
        self.gp = GenParams(test_core_config.replace(start_pc=0x18))
        self.m = TestElaboratable(self.gp)
        self.instr_queue = deque()
        self.iterations = 500

        random.seed(422)

    def cache_processes(self):
        input_q = deque()
        output_q = deque()

        def cache_process():
            yield Passive()

            next_pc = self.gp.start_pc

            while True:
                while len(input_q) == 0:
                    yield

                while random.random() < 0.5:
                    yield

                addr = input_q.popleft()
                is_branch = random.random() < 0.15

                # exclude branches and jumps
                data = random.randrange(2**self.gp.isa.ilen) & ~0b1110000

                # randomize being a branch instruction
                if is_branch:
                    data |= 0b1100000

                output_q.append({"instr": data, "error": 0})

                # Speculative fetch. Skip, because this instruction shouldn't be executed.
                if addr != next_pc:
                    continue

                next_pc = addr + self.gp.isa.ilen_bytes
                if is_branch:
                    next_pc = random.randrange(2**self.gp.isa.ilen) & ~0b11

                self.instr_queue.append(
                    {
                        "data": data,
                        "pc": addr,
                        "is_branch": is_branch,
                        "next_pc": next_pc,
                    }
                )

        @def_method_mock(lambda: self.m.icache.issue_req_io, enable=lambda: len(input_q) < 2, sched_prio=1)
        def issue_req_mock(addr):
            input_q.append(addr)

        @def_method_mock(lambda: self.m.icache.accept_res_io, enable=lambda: len(output_q) > 0)
        def accept_res_mock():
            return output_q.popleft()

        return issue_req_mock, accept_res_mock, cache_process

    def fetch_out_check(self):
        for _ in range(self.iterations):
            while len(self.instr_queue) == 0:
                yield

            instr = self.instr_queue.popleft()
            # important to wait for a particular instruction before calling verify_branch
            v = yield from self.m.io_out.call()
            self.assertEqual(v["pc"], instr["pc"])
            self.assertEqual(v["data"], instr["data"])

            if instr["is_branch"]:
                for _ in range(random.randrange(10)):
                    yield
                yield from self.m.verify_branch.call(from_pc=instr["pc"], next_pc=instr["next_pc"])

    def test(self):
        issue_req_mock, accept_res_mock, cache_process = self.cache_processes()

        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(issue_req_mock)
            sim.add_sync_process(accept_res_mock)
            sim.add_sync_process(cache_process)
            sim.add_sync_process(self.fetch_out_check)
