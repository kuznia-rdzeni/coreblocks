from collections import deque

import random

from amaranth import Elaboratable, Module
from amaranth.sim import Passive, Settle

from coreblocks.transactions import TransactionModule
from coreblocks.transactions.lib import AdapterTrans, FIFO, Adapter
from coreblocks.frontend.fetch import Fetch
from coreblocks.params import GenParams, FetchLayouts, ICacheLayouts
from ..common import TestCaseWithSimulator, TestbenchIO, test_gen_params, def_method_mock


class TestElaboratable(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.gp = gen_params

    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        cache_layouts = self.gp.get(ICacheLayouts)
        self.issue_req_io = TestbenchIO(Adapter(i=cache_layouts.issue_req))
        self.accept_res_io = TestbenchIO(Adapter(o=cache_layouts.accept_res))

        fifo = FIFO(self.gp.get(FetchLayouts).raw_instr, depth=2)
        self.io_out = TestbenchIO(AdapterTrans(fifo.read))
        self.fetch = Fetch(self.gp, self.issue_req_io.adapter.iface, self.accept_res_io.adapter.iface, fifo.write)
        self.verify_branch = TestbenchIO(AdapterTrans(self.fetch.verify_branch))

        m.submodules.issue_req_io = self.issue_req_io
        m.submodules.accept_res_io = self.accept_res_io
        m.submodules.fetch = self.fetch
        m.submodules.io_out = self.io_out
        m.submodules.verify_branch = self.verify_branch
        m.submodules.fifo = fifo

        return tm


class TestFetch(TestCaseWithSimulator):
    def setUp(self) -> None:
        self.gp = test_gen_params("rv32i", start_pc=0x18)
        self.m = TestElaboratable(self.gp)
        self.instr_queue = deque()
        self.iterations = 500

        random.seed(422)

    def cache_processes(self):
        input_q = deque()
        output_q = deque()

        def cache_process():
            yield Passive()

            while True:
                while len(input_q) == 0:
                    yield

                while random.random() < 0.5:
                    yield

                addr = input_q.popleft()
                is_branch = random.random() < 0.15

                # exclude branches and jumps
                data = random.randrange(2**self.gp.isa.ilen) & ~0b1110000
                next_pc = addr + self.gp.isa.ilen_bytes

                # randomize being a branch instruction
                if is_branch:
                    data |= 0b1100000
                    next_pc = random.randrange(2**self.gp.isa.ilen) & ~0b11

                print(f"adding to q addr={addr:x} data={data:x} branch={is_branch}")
                self.instr_queue.append(
                    {
                        "data": data,
                        "pc": addr,
                        "is_branch": is_branch,
                        "next_pc": next_pc,
                    }
                )
                output_q.append({"instr": data, "error": 0})

        @def_method_mock(lambda: self.m.issue_req_io, enable=lambda: len(input_q) < 2, settle=1)
        def issue_req_mock(arg):
            print(f"requesting {arg['addr']:x}")
            input_q.append(arg["addr"])

        @def_method_mock(lambda: self.m.accept_res_io, enable=lambda: len(output_q) > 0, settle=1)
        def accept_res_mock(_):
            v = output_q.popleft()
            print(f"accepting error={v['error']:x} data={v['instr']:x}")
            return v
        
        return issue_req_mock, accept_res_mock, cache_process


    def fetch_out_check(self):
        for _ in range(self.iterations):
            while len(self.instr_queue) == 0:
                yield

            instr = self.instr_queue.popleft()
            if instr["is_branch"]:
                for _ in range(random.randrange(10)):
                    yield
                yield from self.m.verify_branch.call(next_pc=instr["next_pc"])

            v = yield from self.m.io_out.call()
            print(f"check {instr['data']:x}")
            self.assertEqual(v["pc"], instr["pc"])
            self.assertEqual(v["data"], instr["data"])

    def test(self):
        issue_req_mock, accept_res_mock, cache_process = self.cache_processes()

        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(issue_req_mock)
            sim.add_sync_process(accept_res_mock)
            sim.add_sync_process(cache_process)
            sim.add_sync_process(self.fetch_out_check)
