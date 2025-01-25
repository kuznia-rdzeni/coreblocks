from collections import deque
import random
from amaranth import *
from amaranth.utils import ceil_log2
from transactron import TModule
from transactron.lib import Adapter
from transactron.testing import MethodMock, SimpleTestCircuit, TestCaseWithSimulator, TestbenchIO, def_method_mock

from coreblocks.arch.isa_consts import Funct3, Funct7
from coreblocks.arch.optypes import OpType
from coreblocks.func_blocks.fu.lsu.lsu_atomic_wrapper import LSUAtomicWrapper
from coreblocks.func_blocks.interface.func_protocols import FuncUnit
from coreblocks.interface.layouts import FuncUnitLayouts
from coreblocks.params.configurations import test_core_config
from coreblocks.params.genparams import GenParams


class FuncUnitMock(FuncUnit, Elaboratable):
    def __init__(self, gen_params):
        layouts = gen_params.get(FuncUnitLayouts)

        self.issue_tb = TestbenchIO(Adapter.create(i=layouts.issue))
        self.accept_tb = TestbenchIO(Adapter.create(o=layouts.accept))

        self.issue = self.issue_tb.adapter.iface
        self.accept = self.accept_tb.adapter.iface

    def elaborate(self, platform):
        m = TModule()

        m.submodules.issue_tb = self.issue_tb
        m.submodules.accept_tb = self.accept_tb

        return m


class TestLSUAtomicWrapper(TestCaseWithSimulator):
    def setup_method(self):
        random.seed(1258)
        self.inst_cnt = 255
        self.gen_params = GenParams(test_core_config.replace(rob_entries_bits=ceil_log2(self.inst_cnt)))
        self.lsu = FuncUnitMock(self.gen_params)
        self.dut = SimpleTestCircuit(LSUAtomicWrapper(self.gen_params, self.lsu))

        self.mem_cell = 0
        self.instr_q = deque()
        self.results = {}
        self.lsu_res_q = deque()
        self.lsu_except_q = deque()

        self.generate_instrs(self.inst_cnt)

    @def_method_mock(lambda self: self.lsu.issue_tb, enable=lambda _: random.random() < 0.9)
    def lsu_issue_mock(self, arg):
        @MethodMock.effect
        def _():
            res = 0
            addr = arg["s1_val"] + arg["imm"]

            exc = self.lsu_except_q[0]
            self.lsu_except_q.popleft()
            assert addr == exc["addr"]

            if not exc["exception"]:
                match arg["exec_fn"]["op_type"]:
                    case OpType.STORE:
                        self.mem_cell = arg["s2_val"]
                    case OpType.LOAD:
                        res = self.mem_cell
                    case _:
                        assert False

            self.lsu_res_q.append(
                {"rob_id": arg["rob_id"], "result": res, "rp_dst": arg["rp_dst"], "exception": exc["exception"]}
            )

    @def_method_mock(
        lambda self: self.lsu.accept_tb, enable=lambda self: random.random() < 0.9 and len(self.lsu_res_q) > 0
    )
    def lsu_accept_mock(self, arg):
        res = self.lsu_res_q[0]

        @MethodMock.effect
        def _():
            self.lsu_res_q.popleft()

        return res

    def generate_instrs(self, cnt):
        generation_mem_cell = 0
        generation_reservation_valid = 0
        for i in range(cnt):
            optype = random.choice([OpType.LOAD, OpType.STORE, OpType.ATOMIC_MEMORY_OP, OpType.ATOMIC_LR_SC])
            funct7 = 0

            imm = random.randint(0, 1)
            s1_val = random.randrange(0, 2**self.gen_params.isa.xlen - 1)
            s2_val = random.randrange(0, 2**self.gen_params.isa.xlen)
            rp_dst = random.randrange(0, 2**self.gen_params.phys_regs_bits)

            exception = 0
            result = 0

            if optype == OpType.ATOMIC_MEMORY_OP:
                funct7 = random.choice(
                    [
                        Funct7.AMOSWAP,
                        Funct7.AMOADD,
                        Funct7.AMOMAXU,
                        Funct7.AMOMIN,
                        Funct7.AMOXOR,
                        Funct7.AMOOR,
                        Funct7.AMOAND,
                        Funct7.AMOMAX,
                        Funct7.AMOMINU,
                    ]
                )

                exception = random.random() < 0.3
                exception_on_load = exception and random.random() < 0.5
                self.lsu_except_q.append({"addr": s1_val, "exception": exception_on_load})

                if not exception:
                    result = generation_mem_cell

                    def twos(x):
                        if x & (1 << (self.gen_params.isa.xlen - 1)):
                            x ^= (1 << self.gen_params.isa.xlen) - 1
                            x += 1
                            x *= -1
                        return x

                    match funct7:
                        case Funct7.AMOSWAP:
                            generation_mem_cell = s2_val
                        case Funct7.AMOADD:
                            generation_mem_cell += s2_val
                            generation_mem_cell %= 2**self.gen_params.isa.xlen
                        case Funct7.AMOAND:
                            generation_mem_cell &= s2_val
                        case Funct7.AMOOR:
                            generation_mem_cell |= s2_val
                        case Funct7.AMOXOR:
                            generation_mem_cell ^= s2_val
                        case Funct7.AMOMIN:
                            generation_mem_cell = (
                                generation_mem_cell if twos(generation_mem_cell) < twos(s2_val) else s2_val
                            )
                        case Funct7.AMOMAX:
                            generation_mem_cell = (
                                generation_mem_cell if twos(generation_mem_cell) > twos(s2_val) else s2_val
                            )
                        case Funct7.AMOMINU:
                            generation_mem_cell = min(generation_mem_cell, s2_val)
                        case Funct7.AMOMAXU:
                            generation_mem_cell = max(generation_mem_cell, s2_val)

                if not exception_on_load:
                    self.lsu_except_q.append({"addr": s1_val, "exception": exception})
            elif optype == OpType.ATOMIC_LR_SC:
                is_load = random.random() < 0.5
                exception = random.random() < 0.3
                sc_fail = False
                if is_load:
                    funct7 = Funct7.LR
                    generation_reservation_valid = not exception
                    result = generation_mem_cell if not exception else 0
                else:
                    funct7 = Funct7.SC
                    if generation_reservation_valid:
                        if not exception:
                            generation_mem_cell = s2_val
                    else:
                        sc_fail = True
                        exception = 0

                    result = 0 if generation_reservation_valid or exception else 1
                    generation_reservation_valid = 0

                if not sc_fail:
                    self.lsu_except_q.append({"addr": s1_val, "exception": exception})

            elif optype == OpType.LOAD:
                result = generation_mem_cell
                self.lsu_except_q.append({"addr": s1_val + imm, "exception": 0})
            elif optype == OpType.STORE:
                generation_mem_cell = s2_val
                result = 0
                self.lsu_except_q.append({"addr": s1_val + imm, "exception": 0})

            exec_fn = {"op_type": optype, "funct3": Funct3.W, "funct7": funct7}
            rob_id = i
            instr = {
                "rp_dst": rp_dst,
                "rob_id": rob_id,
                "exec_fn": exec_fn,
                "s1_val": s1_val,
                "s2_val": s2_val,
                "imm": imm,
                "pc": 0,
            }
            self.instr_q.append(instr)
            self.results[rob_id] = {"rob_id": rob_id, "rp_dst": rp_dst, "result": result, "exception": exception}

    async def issue_process(self, sim):
        while self.instr_q:
            await self.dut.issue.call(sim, self.instr_q[0])
            self.instr_q.popleft()
            await self.random_wait_geom(sim, 0.9)

    async def accept_process(self, sim):
        for _ in range(self.inst_cnt):
            res = await self.dut.accept.call(sim)
            expected = self.results[res["rob_id"]]
            assert res["rp_dst"] == expected["rp_dst"]
            assert res["exception"] == expected["exception"]
            assert res["result"] == expected["result"]
            await self.random_wait_geom(sim, 0.9)

    def test_randomized(self):
        with self.run_simulation(self.dut, max_cycles=700) as sim:
            sim.add_testbench(self.issue_process)
            sim.add_testbench(self.accept_process)
