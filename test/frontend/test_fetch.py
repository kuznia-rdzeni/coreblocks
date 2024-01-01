from collections import deque

import random

from amaranth import Elaboratable, Module
from amaranth.sim import Passive

from transactron.core import Method
from transactron.lib import AdapterTrans, FIFO, Adapter
from coreblocks.frontend.fetch import Fetch, UnalignedFetch
from coreblocks.frontend.icache import ICacheInterface
from coreblocks.params import *
from coreblocks.params.configurations import test_core_config
from transactron.utils import ModuleConnector
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
        self.gen_params = gen_params

    def elaborate(self, platform):
        m = Module()

        self.icache = MockedICache(self.gen_params)

        fifo = FIFO(self.gen_params.get(FetchLayouts).raw_instr, depth=2)
        self.io_out = TestbenchIO(AdapterTrans(fifo.read))
        self.fetch = Fetch(self.gen_params, self.icache, fifo.write)
        self.verify_branch = TestbenchIO(AdapterTrans(self.fetch.verify_branch))

        m.submodules.icache = self.icache
        m.submodules.fetch = self.fetch
        m.submodules.io_out = self.io_out
        m.submodules.verify_branch = self.verify_branch
        m.submodules.fifo = fifo

        return m


class TestFetch(TestCaseWithSimulator):
    def setUp(self) -> None:
        self.gen_params = GenParams(test_core_config.replace(start_pc=0x18))
        self.m = TestElaboratable(self.gen_params)
        self.instr_queue = deque()
        self.iterations = 500

        random.seed(422)

        self.input_q = deque()
        self.output_q = deque()

    def cache_process(self):
        yield Passive()

        next_pc = self.gen_params.start_pc

        while True:
            while len(self.input_q) == 0:
                yield

            while random.random() < 0.5:
                yield

            addr = self.input_q.popleft()
            is_branch = random.random() < 0.15

            # exclude branches and jumps
            data = random.randrange(2**self.gen_params.isa.ilen) & ~0b1111111

            # randomize being a branch instruction
            if is_branch:
                data |= 0b1100000

            self.output_q.append({"instr": data, "error": 0})

            # Speculative fetch. Skip, because this instruction shouldn't be executed.
            if addr != next_pc:
                continue

            next_pc = addr + self.gen_params.isa.ilen_bytes
            if is_branch:
                next_pc = random.randrange(2**self.gen_params.isa.ilen) & ~0b11

            self.instr_queue.append(
                {
                    "instr": data,
                    "pc": addr,
                    "is_branch": is_branch,
                    "next_pc": next_pc,
                }
            )

    @def_method_mock(lambda self: self.m.icache.issue_req_io, enable=lambda self: len(self.input_q) < 2, sched_prio=1)
    def issue_req_mock(self, addr):
        self.input_q.append(addr)

    @def_method_mock(lambda self: self.m.icache.accept_res_io, enable=lambda self: len(self.output_q) > 0)
    def accept_res_mock(self):
        return self.output_q.popleft()

    def fetch_out_check(self):
        for _ in range(self.iterations):
            while len(self.instr_queue) == 0:
                yield

            instr = self.instr_queue.popleft()
            if instr["is_branch"]:
                yield from self.random_wait(10)
                yield from self.m.verify_branch.call(from_pc=instr["pc"], next_pc=instr["next_pc"])

            v = yield from self.m.io_out.call()
            self.assertEqual(v["pc"], instr["pc"])
            self.assertEqual(v["instr"], instr["instr"])

    def test(self):
        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.cache_process)
            sim.add_sync_process(self.fetch_out_check)


class TestUnalignedFetch(TestCaseWithSimulator):
    def setUp(self) -> None:
        self.gen_params = GenParams(test_core_config.replace(start_pc=0x18, compressed=True))
        self.instr_queue = deque()
        self.instructions = 500

        self.icache = MockedICache(self.gen_params)
        fifo = FIFO(self.gen_params.get(FetchLayouts).raw_instr, depth=2)
        self.io_out = TestbenchIO(AdapterTrans(fifo.read))
        fetch = UnalignedFetch(self.gen_params, self.icache, fifo.write)
        self.verify_branch = TestbenchIO(AdapterTrans(fetch.verify_branch))

        self.m = ModuleConnector(self.icache, fifo, self.io_out, fetch, self.verify_branch)

        self.mem = {}
        self.memerr = set()

        random.seed(422)
        self.input_q = deque()
        self.output_q = deque()

    def gen_instr_seq(self):
        pc = self.gen_params.start_pc

        for _ in range(self.instructions):
            is_branch = random.random() < 0.15
            is_rvc = random.random() < 0.5
            branch_target = random.randrange(2**self.gen_params.isa.ilen) & ~0b1

            error = random.random() < 0.1

            if is_rvc:
                data = (random.randrange(11) << 2) | 0b01  # C.ADDI
                if is_branch:
                    data = data | (0b101 << 13)  # make it C.J

                self.mem[pc] = data
                if error:
                    self.memerr.add(pc)
            else:
                data = random.randrange(2**self.gen_params.isa.ilen) & ~0b1111111
                data |= 0b11  # 2 lowest bits must be set in 32-bit long instructions
                if is_branch:
                    data |= 0b1100000

                self.mem[pc] = data & 0xFFFF
                self.mem[pc + 2] = data >> 16
                if error:
                    self.memerr.add(random.choice([pc, pc + 2]))

            next_pc = pc + (2 if is_rvc else 4)
            if is_branch:
                next_pc = branch_target

            self.instr_queue.append(
                {
                    "pc": pc,
                    "is_branch": is_branch,
                    "next_pc": next_pc,
                    "rvc": is_rvc,
                }
            )

            pc = next_pc

    def cache_process(self):
        yield Passive()

        while True:
            while len(self.input_q) == 0:
                yield

            while random.random() < 0.5:
                yield

            req_addr = self.input_q.popleft()

            def get_mem_or_random(addr):
                return self.mem[addr] if addr in self.mem else random.randrange(2**16)

            data = (get_mem_or_random(req_addr + 2) << 16) | get_mem_or_random(req_addr)

            err = (req_addr in self.memerr) or (req_addr + 2 in self.memerr)
            self.output_q.append({"instr": data, "error": err})

    @def_method_mock(lambda self: self.icache.issue_req_io, enable=lambda self: len(self.input_q) < 2, sched_prio=1)
    def issue_req_mock(self, addr):
        self.input_q.append(addr)

    @def_method_mock(lambda self: self.icache.accept_res_io, enable=lambda self: len(self.output_q) > 0)
    def accept_res_mock(self):
        return self.output_q.popleft()

    def fetch_out_check(self):
        while self.instr_queue:
            instr = self.instr_queue.popleft()

            instr_error = (instr["pc"] & (~0b11)) in self.memerr or (instr["pc"] & (~0b11)) + 2 in self.memerr
            if instr["pc"] & 2 and not instr["rvc"]:
                instr_error |= ((instr["pc"] + 2) & (~0b11)) in self.memerr or (
                    (instr["pc"] + 2) & (~0b11)
                ) + 2 in self.memerr

            v = yield from self.io_out.call()
            self.assertEqual(v["pc"], instr["pc"])
            self.assertEqual(v["access_fault"], instr_error)

            if instr["is_branch"] or instr_error:
                yield from self.random_wait(10)
                yield from self.verify_branch.call(next_pc=instr["next_pc"])

    def test(self):
        self.gen_instr_seq()

        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.cache_process)
            sim.add_sync_process(self.fetch_out_check)
