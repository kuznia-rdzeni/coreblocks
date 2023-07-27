import random
from typing import Optional

from amaranth import *

from coreblocks.transactions.lib import Adapter, AdapterTrans
from coreblocks.params import OpType, GenParams
from coreblocks.lsu.dummyLsu import LSUDummy
from coreblocks.params.configurations import test_core_config
from coreblocks.params.isa import *
from coreblocks.params.keys import ExceptionReportKey
from coreblocks.params.dependencies import DependencyManager
from coreblocks.params.layouts import ExceptionRegisterLayouts
from coreblocks.peripherals.wishbone import WishboneParameters
from coreblocks.utils import LayoutLike
from test.common import TestCaseWithSimulator, int_to_signed, signed_to_int
from test.transactional_testing import Sim, SimFIFO, WaitSettled


def generate_register(xlen: int, phys_regs_bits: int) -> tuple[int, int, Optional[dict[str, int]], int]:
    real_val = random.randrange(0, 2**xlen)
    if random.randint(0, 1):
        rp = random.randint(1, 2**phys_regs_bits - 1)
        val = 0
        ann_data = {"tag": rp, "value": real_val}
    else:
        rp = 0
        val = real_val
        ann_data = None
    return rp, val, ann_data, real_val


def generate_random_op(ops: list[tuple[OpType, Funct3]]) -> tuple[tuple[OpType, Funct3], int, bool]:
    op = random.choice(ops)
    signed = False
    num_bytes = 4
    if op[1] in {Funct3.B, Funct3.BU}:
        num_bytes = 1
    if op[1] in {Funct3.H, Funct3.HU}:
        num_bytes = 2
    if op[1] in {Funct3.B, Funct3.H}:
        signed = True
    return (op, num_bytes, signed)


def generate_imm() -> int:
    if random.randint(0, 1):
        return 0
    else:
        return random.randint(-2**11, 2**11-1)


def calculate_wb_sel(addr: int, num_bytes: int) -> tuple[int, int]:
    rest = addr % 4
    wb_addr = addr >> 2
    wb_sel = (2 ** num_bytes - 1) << rest
    return wb_addr, wb_sel


def check_align(addr: int, op: tuple[OpType, Funct3]) -> bool:
    rest = addr % 4
    if op[1] in {Funct3.B, Funct3.BU}:
        return True
    if op[1] in {Funct3.H, Funct3.HU} and rest in {0, 2}:
        return True
    if op[1] == Funct3.W and rest == 0:
        return True
    return False


class WishboneMasterStub(Elaboratable):
    def __init__(self, wb_params: WishboneParameters):
        # initialisation taken from peripherals/wishbone.py -- maybe there is possibility to make it common?
        self.wb_params = wb_params
        self.generate_layouts(wb_params)

        self.request_adapter = Adapter(i=self.requestLayout)
        self.request = self.request_adapter.iface
        self.result_adapter = Adapter(o=self.resultLayout)
        self.result = self.result_adapter.iface

    def generate_layouts(self, wb_params: WishboneParameters):
        # generate method layouts locally
        self.requestLayout: LayoutLike = [
            ("addr", wb_params.addr_width),
            ("data", wb_params.data_width),
            ("we", 1),
            ("sel", wb_params.data_width // wb_params.granularity),
        ]

        self.resultLayout: LayoutLike = [("data", wb_params.data_width), ("err", 1)]

    def elaborate(self, platform):
        m = Module()

        m.submodules.request_adapter = self.request_adapter
        m.submodules.result_adapter = self.result_adapter

        return m


class DummyLSUTestCircuit(Elaboratable):
    def __init__(self, gen: GenParams):
        self.gen = gen

    def elaborate(self, platform):
        m = Module()

        wb_params = WishboneParameters(
            data_width=self.gen.isa.ilen,
            addr_width=32,
        )

        self.bus = WishboneMasterStub(wb_params)

        m.submodules.exception_report = self.exception_report = Adapter(i=self.gen.get(ExceptionRegisterLayouts).report)

        self.gen.get(DependencyManager).add_dependency(ExceptionReportKey(), self.exception_report.iface)

        m.submodules.func_unit = func_unit = LSUDummy(self.gen, self.bus)

        m.submodules.select_mock = self.select = AdapterTrans(func_unit.select)
        m.submodules.insert_mock = self.insert = AdapterTrans(func_unit.insert)
        m.submodules.update_mock = self.update = AdapterTrans(func_unit.update)
        m.submodules.get_result_mock = self.get_result = AdapterTrans(func_unit.get_result)
        m.submodules.precommit_mock = self.precommit = AdapterTrans(func_unit.precommit)
        m.submodules.bus = self.bus
        return m


class TestDummyLSU(TestCaseWithSimulator):
    def generate_instr(self):
        ops = [
            (OpType.LOAD, Funct3.B),
            (OpType.LOAD, Funct3.BU),
            (OpType.LOAD, Funct3.H),
            (OpType.LOAD, Funct3.HU),
            (OpType.LOAD, Funct3.W),
            (OpType.STORE, Funct3.B),
            (OpType.STORE, Funct3.H),
            (OpType.STORE, Funct3.W),
        ]
        for i in range(self.tests_number):
            misaligned = False
            bus_err = random.random() < 0.1

            (op, num_bytes, signed) = generate_random_op(ops)

            # generate addresses till we generate correct one
            while True:
                # generate rp1, val1 which create addr
                rp_s1, s1_val, ann_data1, arg1_val = generate_register(self.gp.isa.xlen, self.gp.phys_regs_bits)
                imm = generate_imm()
                addr = arg1_val + imm

                if check_align(addr, op):
                    break

                if random.random() < 0.1:
                    misaligned = True
                    break

            rp_s2 = 0
            s2_val = 0
            ann_data2 = None
            req_data = 0
            resp_data = 0
            cause = None
            if op[0] == OpType.STORE:
                rp_s2, s2_val, ann_data2, arg2_val = generate_register(self.gp.isa.xlen, self.gp.phys_regs_bits)
                if rp_s1 == rp_s2 and ann_data1 is not None and ann_data2 is not None:
                    ann_data2 = None
                    arg2_val = arg1_val
                req_data = arg2_val
                we = True
                if misaligned:
                    cause = ExceptionCause.STORE_ADDRESS_MISALIGNED
                elif bus_err:
                    cause = ExceptionCause.STORE_ACCESS_FAULT
            else:
                resp_data = random.randint(0, 2**32 - 1)
                we = False
                if misaligned:
                    cause = ExceptionCause.LOAD_ADDRESS_MISALIGNED
                elif bus_err:
                    cause = ExceptionCause.LOAD_ACCESS_FAULT

            exec_fn = {"op_type": op[0], "funct3": op[1], "funct7": 0}

            rp_dst = random.randrange(0, 2**self.gp.phys_regs_bits)
            rob_id = random.randrange(0, 2**self.gp.rob_entries_bits)
            instr_data = {
                "rp_s1": rp_s1,
                "rp_s2": rp_s2,
                "rp_dst": rp_dst,
                "rob_id": rob_id,
                "exec_fn": exec_fn,
                "s1_val": s1_val,
                "s2_val": s2_val,
                "imm": imm,
            }
            mem_data = {
                "addr": addr,
                "num_bytes": num_bytes,
                "sign": signed,
                "we": we,
                "req_data": req_data,
                "resp_data": resp_data,
                "misaligned": misaligned,
                "err": bus_err,
            }
            exc_data = (
                {
                    "rob_id": rob_id,
                    "cause": cause
                }
                if cause is not None
                else None
            )
            ann_data = []
            if ann_data1 is not None:
                ann_data.append(ann_data1)
            if ann_data2 is not None:
                ann_data.append(ann_data2)
            random.shuffle(ann_data)
            self.instr_queue.init_push({"instr": instr_data, "ann": ann_data, "mem": mem_data, "exc": exc_data})

    def setUp(self) -> None:
        random.seed(14)
        self.tests_number = 100
        self.gp = GenParams(test_core_config.replace(phys_regs_bits=3, rob_entries_bits=3))
        self.test_module = DummyLSUTestCircuit(self.gp)
        self.instr_queue = SimFIFO()
        self.mem_data_queue = SimFIFO()
        self.mem_result_queue = SimFIFO()
        self.returned_data = SimFIFO()
        self.exception_queue = SimFIFO()
        self.exception_result = SimFIFO()
        self.generate_instr()
        self.announce_queue = SimFIFO()
        self.precommit_queue = SimFIFO()

    @Sim.def_method_mock(
        lambda self: self.test_module.bus.request_adapter,
        enable=lambda self: self.mem_data_queue.not_empty(),
        max_delay=10,
        enabled_active=True,
    )
    async def wishbone_request(self, addr, data, we, sel):
        generated_data = await self.mem_data_queue.pop()
        num_bytes = generated_data["num_bytes"]
        sign = generated_data["sign"]
        exp_addr, exp_sel = calculate_wb_sel(generated_data["addr"], num_bytes)

        await WaitSettled()

        resp_data = generated_data["resp_data"]
        data_shift = (exp_sel & -exp_sel).bit_length() - 1
        w_data = (generated_data["req_data"] & (2 ** (num_bytes * 8) - 1)) << (data_shift * 8)

        self.assertEqual(addr, exp_addr)
        self.assertEqual(data, w_data)
        self.assertEqual(we, generated_data["we"])
        self.assertEqual(sel, exp_sel)

        assert exp_sel.bit_length() == data_shift + exp_sel.bit_count(), "Unexpected mask"

        if not generated_data["err"]:
            ret_data = resp_data >> (data_shift * 8)
            ret_data &= (2 ** (num_bytes * 8) - 1)
            if sign:
                ret_data = int_to_signed(signed_to_int(ret_data, num_bytes*8), 32)
            await self.returned_data.push(ret_data)

        await self.mem_result_queue.push({"data": resp_data, "err": generated_data["err"]})

    @Sim.def_method_mock(
        lambda self: self.test_module.bus.result_adapter,
        enable=lambda self: self.mem_result_queue.not_empty(),
        enabled_active=True,
    )
    async def wishbone_result(self):
        return await self.mem_result_queue.pop()

    @Sim.queue_reader(lambda self: self.instr_queue, max_delay=10)
    async def inserter(self, req):
        ret = await Sim.call(self.test_module.select)
        self.assertEqual(ret["rs_entry_id"], 0)

        await Sim.call(self.test_module.insert, rs_data=req["instr"], rs_entry_id=0)

        await self.precommit_queue.push(req["instr"]["rob_id"])
        if not req["mem"]["misaligned"]:
            await self.mem_data_queue.push(req["mem"])
        if req["ann"] is not None:
            for ann in req["ann"]:
                await self.announce_queue.push(ann)
        await self.exception_result.push(req["exc"] is not None)
        if req["exc"] is not None:
            await self.exception_queue.push(req["exc"])

    @Sim.queue_reader(lambda self: self.announce_queue, max_delay=10)
    async def announcer(self, announc):
        await Sim.call(self.test_module.update, announc)

    async def precommitter(self):
        await Sim.passive()
        if await self.precommit_queue.not_empty():
            rob_id = await self.precommit_queue.peek()
            await Sim.call(self.test_module.precommit, rob_id=rob_id)

    @Sim.def_method_mock(
        lambda self: self.test_module.get_result, max_delay=10, active=lambda self: self.exception_result.not_empty()
    )
    async def consumer(self, arg):
        await WaitSettled()
        exc = await self.exception_result.pop()
        await self.precommit_queue.pop()
        if not exc:
            self.assertEqual(arg["result"], await self.returned_data.pop())
        self.assertEqual(arg["exception"], exc)

    @Sim.def_method_mock(
        lambda self: self.test_module.exception_report, active=lambda self: self.exception_queue.not_empty()
    )
    async def exception_consumer(self, arg):
        await WaitSettled()
        self.assertDictEqual(arg, await self.exception_queue.pop())

    def test(self):
        with self.run_simulation(self.test_module) as sim:
            tsim = Sim()
            tsim.add_process(self.wishbone_request)
            tsim.add_process(self.wishbone_result)
            tsim.add_process(self.inserter)
            tsim.add_process(self.announcer)
            tsim.add_process(self.consumer)
            tsim.add_process(self.precommitter)
            tsim.add_process(self.exception_consumer)
            sim.add_sync_process(tsim.process)


# class TestDummyLSULoadsCycles(TestCaseWithSimulator):
#    def generate_instr(self, max_reg_val, max_imm_val):
#        s1_val = random.randint(0, max_reg_val // 4) * 4
#        imm = random.randint(0, max_imm_val // 4) * 4
#        rp_dst = random.randint(0, 2**self.gp.phys_regs_bits - 1)
#        rob_id = random.randint(0, 2**self.gp.rob_entries_bits - 1)
#
#        exec_fn = {"op_type": OpType.LOAD, "funct3": Funct3.W, "funct7": 0}
#        instr = {
#            "rp_s1": 0,
#            "rp_s2": 0,
#            "rp_dst": rp_dst,
#            "rob_id": rob_id,
#            "exec_fn": exec_fn,
#            "s1_val": s1_val,
#            "s2_val": 0,
#            "imm": imm,
#        }
#
#        wish_data = {
#            "addr": (s1_val + imm) >> 2,
#            "mask": 0xF,
#            "rnd_bytes": bytes.fromhex(f"{random.randint(0,2**32-1):08x}"),
#        }
#        return instr, wish_data
#
#    def setUp(self) -> None:
#        random.seed(14)
#        self.gp = GenParams(test_core_config.replace(phys_regs_bits=3, rob_entries_bits=3))
#        self.test_module = DummyLSUTestCircuit(self.gp)
#
#    def one_instr_test(self):
#        instr, wish_data = self.generate_instr(2**7, 2**7)
#
#        ret = yield from self.test_module.select.call()
#        self.assertEqual(ret["rs_entry_id"], 0)
#        yield from self.test_module.insert.call(rs_data=instr, rs_entry_id=1)
#        yield from self.test_module.io_in.slave_wait()
#
#        mask = wish_data["mask"]
#        yield from self.test_module.io_in.slave_verify(wish_data["addr"], 0, 0, mask)
#        data = wish_data["rnd_bytes"][:4]
#        data = int(data.hex(), 16)
#        yield from self.test_module.io_in.slave_respond(data)
#        yield Settle()
#
#        v = yield from self.test_module.get_result.call()
#        self.assertEqual(v["result"], data)
#
#    def test(self):
#        @def_method_mock(lambda: self.test_module.exception_report)
#        def exception_consumer(arg):
#            self.assertTrue(False)
#
#        with self.run_simulation(self.test_module) as sim:
#            sim.add_sync_process(self.one_instr_test)
#            sim.add_sync_process(exception_consumer)
#
#
# class TestDummyLSUFence(TestCaseWithSimulator):
#    def get_instr(self, exec_fn):
#        return {
#            "rp_s1": 0,
#            "rp_s2": 0,
#            "rp_dst": 1,
#            "rob_id": 1,
#            "exec_fn": exec_fn,
#            "s1_val": 4,
#            "s2_val": 1,
#            "imm": 8,
#        }
#
#    def push_one_instr(self, instr):
#        yield from self.test_module.select.call()
#        yield from self.test_module.insert.call(rs_data=instr, rs_entry_id=1)
#
#        if instr["exec_fn"]["op_type"] == OpType.LOAD:
#            yield from self.test_module.io_in.slave_wait()
#            yield from self.test_module.io_in.slave_respond(1)
#            yield Settle()
#        v = yield from self.test_module.get_result.call()
#        if instr["exec_fn"]["op_type"] == OpType.LOAD:
#            self.assertEqual(v["result"], 1)
#
#    def process(self):
#        # just tests if FENCE doens't hang up the LSU
#        load_fn = {"op_type": OpType.LOAD, "funct3": Funct3.W, "funct7": 0}
#        fence_fn = {"op_type": OpType.FENCE, "funct3": 0, "funct7": 0}
#        yield from self.push_one_instr(self.get_instr(load_fn))
#        yield from self.push_one_instr(self.get_instr(fence_fn))
#        yield from self.push_one_instr(self.get_instr(load_fn))
#
#    def test_fence(self):
#        self.gp = GenParams(test_core_config.replace(phys_regs_bits=3, rob_entries_bits=3))
#        self.test_module = DummyLSUTestCircuit(self.gp)
#
#        @def_method_mock(lambda: self.test_module.exception_report)
#        def exception_consumer(arg):
#            self.assertTrue(False)
#
#        with self.run_simulation(self.test_module) as sim:
#            sim.add_sync_process(self.process)
#            sim.add_sync_process(exception_consumer)
