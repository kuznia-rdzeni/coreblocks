import random
from collections import deque
from typing import Optional

from amaranth.sim import Settle, Passive

from transactron.lib import Adapter
from coreblocks.params import OpType, GenParams
from coreblocks.lsu.dummyLsu import LSUDummy
from coreblocks.params.configurations import test_core_config
from coreblocks.params.isa import *
from coreblocks.params.keys import ExceptionReportKey
from coreblocks.params.dependencies import DependencyManager
from coreblocks.params.layouts import ExceptionRegisterLayouts
from coreblocks.peripherals.wishbone import *
from test.common import TestbenchIO, TestCaseWithSimulator, def_method_mock, int_to_signed, signed_to_int
from test.peripherals.test_wishbone import WishboneInterfaceWrapper


def generate_register(max_reg_val: int, phys_regs_bits: int) -> tuple[int, int, Optional[dict[str, int]], int]:
    if random.randint(0, 1):
        rp = random.randint(1, 2**phys_regs_bits - 1)
        val = 0
        real_val = random.randint(0, max_reg_val // 4) * 4
        ann_data = {"tag": rp, "value": real_val}
    else:
        rp = 0
        val = random.randint(0, max_reg_val // 4) * 4
        real_val = val
        ann_data = None
    return rp, val, ann_data, real_val


def generate_random_op(ops: dict[str, tuple[OpType, Funct3]]) -> tuple[tuple[OpType, Funct3], int, bool]:
    ops_k = list(ops.keys())
    op = ops[ops_k[random.randint(0, len(ops) - 1)]]
    signess = False
    mask = 0xF
    if op[1] in {Funct3.B, Funct3.BU}:
        mask = 0x1
    if op[1] in {Funct3.H, Funct3.HU}:
        mask = 0x3
    if op[1] in {Funct3.B, Funct3.H}:
        signess = True
    return (op, mask, signess)


def generate_imm(max_imm_val: int) -> int:
    if random.randint(0, 1):
        return 0
    else:
        return random.randint(0, max_imm_val)


def shift_mask_based_on_addr(mask: int, addr: int) -> int:
    rest = addr % 4
    if mask == 0x1:
        mask = mask << rest
    elif mask == 0x3:
        mask = mask << rest
    return mask


def check_align(addr: int, op: tuple[OpType, Funct3]) -> bool:
    rest = addr % 4
    if op[1] in {Funct3.B, Funct3.BU}:
        return True
    if op[1] in {Funct3.H, Funct3.HU} and rest in {0, 2}:
        return True
    if op[1] == Funct3.W and rest == 0:
        return True
    return False


class DummyLSUTestCircuit(Elaboratable):
    def __init__(self, gen: GenParams):
        self.gen = gen

    def elaborate(self, platform):
        m = Module()

        wb_params = WishboneParameters(
            data_width=self.gen.isa.ilen,
            addr_width=32,
        )

        self.bus = WishboneMaster(wb_params)

        m.submodules.exception_report = self.exception_report = TestbenchIO(
            Adapter(i=self.gen.get(ExceptionRegisterLayouts).report)
        )

        self.gen.get(DependencyManager).add_dependency(ExceptionReportKey(), self.exception_report.adapter.iface)

        m.submodules.func_unit = func_unit = LSUDummy(self.gen, self.bus)

        m.submodules.select_mock = self.select = TestbenchIO(AdapterTrans(func_unit.select))
        m.submodules.insert_mock = self.insert = TestbenchIO(AdapterTrans(func_unit.insert))
        m.submodules.update_mock = self.update = TestbenchIO(AdapterTrans(func_unit.update))
        m.submodules.get_result_mock = self.get_result = TestbenchIO(AdapterTrans(func_unit.get_result))
        m.submodules.precommit_mock = self.precommit = TestbenchIO(AdapterTrans(func_unit.precommit))
        m.submodules.clear_mock = self.clear = TestbenchIO(AdapterTrans(func_unit.clear))
        self.io_in = WishboneInterfaceWrapper(self.bus.wbMaster)
        m.submodules.bus = self.bus
        return m


class TestDummyLSULoads(TestCaseWithSimulator):
    def generate_instr(self, max_reg_val, max_imm_val):
        ops = {
            "LB": (OpType.LOAD, Funct3.B),
            "LBU": (OpType.LOAD, Funct3.BU),
            "LH": (OpType.LOAD, Funct3.H),
            "LHU": (OpType.LOAD, Funct3.HU),
            "LW": (OpType.LOAD, Funct3.W),
        }
        for i in range(self.tests_number):
            misaligned = False
            bus_err = random.random() < 0.1

            # generate new instructions till we generate correct one
            while True:
                # generate opcode
                (op, mask, signess) = generate_random_op(ops)
                # generate rp1, val1 which create addr
                rp_s1, s1_val, ann_data, addr = generate_register(max_reg_val, self.gp.phys_regs_bits)
                imm = generate_imm(max_imm_val)
                addr += imm

                if check_align(addr, op):
                    break

                if random.random() < 0.1:
                    misaligned = True
                    break

            self.announce_queue.append(ann_data)
            exec_fn = {"op_type": op[0], "funct3": op[1], "funct7": 0}

            # calculate word address and mask
            mask = shift_mask_based_on_addr(mask, addr)
            addr = addr >> 2

            rp_dst = random.randint(0, 2**self.gp.phys_regs_bits - 1)
            rob_id = random.randint(0, 2**self.gp.rob_entries_bits - 1)
            instr = {
                "rp_s1": rp_s1,
                "rp_s2": 0,
                "rp_dst": rp_dst,
                "rob_id": rob_id,
                "exec_fn": exec_fn,
                "s1_val": s1_val,
                "s2_val": 0,
                "imm": imm,
            }
            self.instr_queue.append(instr)
            self.mem_data_queue.append(
                {
                    "addr": addr,
                    "mask": mask,
                    "sign": signess,
                    "rnd_bytes": bytes.fromhex(f"{random.randint(0,2**32-1):08x}"),
                    "misaligned": misaligned,
                    "err": bus_err,
                }
            )

            if misaligned or bus_err:
                self.exception_queue.append(
                    {
                        "rob_id": rob_id,
                        "cause": ExceptionCause.LOAD_ADDRESS_MISALIGNED
                        if misaligned
                        else ExceptionCause.LOAD_ACCESS_FAULT,
                    }
                )

            self.exception_result.append(
                misaligned or bus_err,
            )

    def setUp(self) -> None:
        random.seed(14)
        self.tests_number = 100
        self.gp = GenParams(test_core_config.replace(phys_regs_bits=3, rob_entries_bits=3))
        self.test_module = DummyLSUTestCircuit(self.gp)
        self.instr_queue = deque()
        self.announce_queue = deque()
        self.mem_data_queue = deque()
        self.returned_data = deque()
        self.exception_queue = deque()
        self.exception_result = deque()
        self.generate_instr(2**7, 2**7)

    def random_wait(self):
        for i in range(random.randint(0, 10)):
            yield

    def wishbone_slave(self):
        yield Passive()

        while True:
            yield from self.test_module.io_in.slave_wait()
            generated_data = self.mem_data_queue.pop()

            if generated_data["misaligned"]:
                continue

            mask = generated_data["mask"]
            sign = generated_data["sign"]
            yield from self.test_module.io_in.slave_verify(generated_data["addr"], 0, 0, mask)
            yield from self.random_wait()

            resp_data = int((generated_data["rnd_bytes"][:4]).hex(), 16)
            data_shift = (mask & -mask).bit_length() - 1
            assert mask.bit_length() == data_shift + mask.bit_count(), "Unexpected mask"

            size = mask.bit_count() * 8
            data_mask = 2**size - 1
            data = (resp_data >> (data_shift * 8)) & data_mask
            if sign:
                data = int_to_signed(signed_to_int(data, size), 32)
            if not generated_data["err"]:
                self.returned_data.append(data)
            yield from self.test_module.io_in.slave_respond(resp_data, err=generated_data["err"])
            yield Settle()

    def inserter(self):
        for i in range(self.tests_number):
            req = self.instr_queue.pop()
            ret = yield from self.test_module.select.call()
            self.assertEqual(ret["rs_entry_id"], 0)
            yield from self.test_module.insert.call(rs_data=req, rs_entry_id=1)
            announc = self.announce_queue.pop()
            if announc is not None:
                yield from self.test_module.update.call(announc)
            yield from self.random_wait()

    def consumer(self):
        for i in range(self.tests_number):
            v = yield from self.test_module.get_result.call()
            exc = self.exception_result.pop()
            if not exc:
                self.assertEqual(v["result"], self.returned_data.pop())
            self.assertEqual(v["exception"], exc)

            yield from self.random_wait()

    def test(self):
        @def_method_mock(lambda: self.test_module.exception_report)
        def exception_consumer(arg):
            self.assertDictEqual(arg, self.exception_queue.pop())

        with self.run_simulation(self.test_module) as sim:
            sim.add_sync_process(self.wishbone_slave)
            sim.add_sync_process(self.inserter)
            sim.add_sync_process(self.consumer)
            sim.add_sync_process(exception_consumer)


class TestDummyLSULoadsCycles(TestCaseWithSimulator):
    def generate_instr(self, max_reg_val, max_imm_val):
        s1_val = random.randint(0, max_reg_val // 4) * 4
        imm = random.randint(0, max_imm_val // 4) * 4
        rp_dst = random.randint(0, 2**self.gp.phys_regs_bits - 1)
        rob_id = random.randint(0, 2**self.gp.rob_entries_bits - 1)

        exec_fn = {"op_type": OpType.LOAD, "funct3": Funct3.W, "funct7": 0}
        instr = {
            "rp_s1": 0,
            "rp_s2": 0,
            "rp_dst": rp_dst,
            "rob_id": rob_id,
            "exec_fn": exec_fn,
            "s1_val": s1_val,
            "s2_val": 0,
            "imm": imm,
        }

        wish_data = {
            "addr": (s1_val + imm) >> 2,
            "mask": 0xF,
            "rnd_bytes": bytes.fromhex(f"{random.randint(0,2**32-1):08x}"),
        }
        return instr, wish_data

    def setUp(self) -> None:
        random.seed(14)
        self.gp = GenParams(test_core_config.replace(phys_regs_bits=3, rob_entries_bits=3))
        self.test_module = DummyLSUTestCircuit(self.gp)

    def one_instr_test(self):
        instr, wish_data = self.generate_instr(2**7, 2**7)

        ret = yield from self.test_module.select.call()
        self.assertEqual(ret["rs_entry_id"], 0)
        yield from self.test_module.insert.call(rs_data=instr, rs_entry_id=1)
        yield from self.test_module.io_in.slave_wait()

        mask = wish_data["mask"]
        yield from self.test_module.io_in.slave_verify(wish_data["addr"], 0, 0, mask)
        data = wish_data["rnd_bytes"][:4]
        data = int(data.hex(), 16)
        yield from self.test_module.io_in.slave_respond(data)
        yield Settle()

        v = yield from self.test_module.get_result.call()
        self.assertEqual(v["result"], data)

    def test(self):
        @def_method_mock(lambda: self.test_module.exception_report)
        def exception_consumer(arg):
            self.assertTrue(False)

        with self.run_simulation(self.test_module) as sim:
            sim.add_sync_process(self.one_instr_test)
            sim.add_sync_process(exception_consumer)


class TestDummyLSUStores(TestCaseWithSimulator):
    def generate_instr(self, max_reg_val, max_imm_val):
        ops = {
            "SB": (OpType.STORE, Funct3.B),
            "SH": (OpType.STORE, Funct3.H),
            "SW": (OpType.STORE, Funct3.W),
        }
        for i in range(self.tests_number):
            while True:
                # generate opcode
                (op, mask, _) = generate_random_op(ops)
                # generate rp1, val1 which create addr
                rp_s1, s1_val, ann_data1, addr = generate_register(max_reg_val, self.gp.phys_regs_bits)
                imm = generate_imm(max_imm_val)
                addr += imm
                if check_align(addr, op):
                    break

            rp_s2, s2_val, ann_data2, data = generate_register(0xFFFFFFFF, self.gp.phys_regs_bits)
            if rp_s1 == rp_s2 and ann_data1 is not None and ann_data2 is not None:
                ann_data2 = None
                data = ann_data1["value"]
            # decide in which order we would get announcments
            if random.randint(0, 1):
                self.announce_queue.append((ann_data1, ann_data2))
            else:
                self.announce_queue.append((ann_data2, ann_data1))

            exec_fn = {"op_type": op[0], "funct3": op[1], "funct7": 0}

            # calculate word address and mask
            mask = shift_mask_based_on_addr(mask, addr)
            addr = addr >> 2

            rob_id = random.randint(0, 2**self.gp.rob_entries_bits - 1)
            instr = {
                "rp_s1": rp_s1,
                "rp_s2": rp_s2,
                "rp_dst": 0,
                "rob_id": rob_id,
                "exec_fn": exec_fn,
                "s1_val": s1_val,
                "s2_val": s2_val,
                "imm": imm,
            }
            self.instr_queue.append(instr)
            self.mem_data_queue.append({"addr": addr, "mask": mask, "data": bytes.fromhex(f"{data:08x}")})

    def setUp(self) -> None:
        random.seed(14)
        self.tests_number = 100
        self.gp = GenParams(test_core_config.replace(phys_regs_bits=3, rob_entries_bits=3))
        self.test_module = DummyLSUTestCircuit(self.gp)
        self.instr_queue = deque()
        self.announce_queue = deque()
        self.mem_data_queue = deque()
        self.get_result_data = deque()
        self.precommit_data = deque()
        self.generate_instr(2**7, 2**7)

    def random_wait(self):
        for i in range(random.randint(0, 8)):
            yield

    def wishbone_slave(self):
        for i in range(self.tests_number):
            yield from self.test_module.io_in.slave_wait()
            generated_data = self.mem_data_queue.pop()

            mask = generated_data["mask"]
            b_dict = {1: 0, 2: 8, 4: 16, 8: 24}
            h_dict = {3: 0, 0xC: 16}
            if mask in b_dict:
                data = (int(generated_data["data"][-1:].hex(), 16) & 0xFF) << b_dict[mask]
            elif mask in h_dict:
                data = (int(generated_data["data"][-2:].hex(), 16) & 0xFFFF) << h_dict[mask]
            else:
                data = int(generated_data["data"][-4:].hex(), 16)
            yield from self.test_module.io_in.slave_verify(generated_data["addr"], data, 1, mask)
            yield from self.random_wait()

            yield from self.test_module.io_in.slave_respond(0)
            yield Settle()

    def inserter(self):
        for i in range(self.tests_number):
            req = self.instr_queue.pop()
            self.get_result_data.appendleft(req["rob_id"])
            ret = yield from self.test_module.select.call()
            self.assertEqual(ret["rs_entry_id"], 0)
            yield from self.test_module.insert.call(rs_data=req, rs_entry_id=0)
            self.precommit_data.appendleft(req["rob_id"])
            announc = self.announce_queue.pop()
            for j in range(2):
                if announc[j] is not None:
                    yield from self.random_wait()
                    yield from self.test_module.update.call(announc[j])
            yield from self.random_wait()

    def get_resulter(self):
        for i in range(self.tests_number):
            v = yield from self.test_module.get_result.call()
            rob_id = self.get_result_data.pop()
            self.assertEqual(v["rob_id"], rob_id)
            self.assertEqual(v["rp_dst"], 0)
            yield from self.random_wait()
            self.precommit_data.pop()  # retire

    def precommiter(self):
        yield Passive()
        while True:
            while len(self.precommit_data) == 0:
                yield
            rob_id = self.precommit_data[-1]  # precommit is called continously until instruction is retired
            yield from self.test_module.precommit.call(rob_id=rob_id)

    def test(self):
        @def_method_mock(lambda: self.test_module.exception_report)
        def exception_consumer(arg):
            self.assertTrue(False)

        with self.run_simulation(self.test_module) as sim:
            sim.add_sync_process(self.wishbone_slave)
            sim.add_sync_process(self.inserter)
            sim.add_sync_process(self.get_resulter)
            sim.add_sync_process(self.precommiter)
            sim.add_sync_process(exception_consumer)


class TestDummyLSUFence(TestCaseWithSimulator):
    def get_instr(self, exec_fn):
        return {
            "rp_s1": 0,
            "rp_s2": 0,
            "rp_dst": 1,
            "rob_id": 1,
            "exec_fn": exec_fn,
            "s1_val": 4,
            "s2_val": 1,
            "imm": 8,
        }

    def push_one_instr(self, instr):
        yield from self.test_module.select.call()
        yield from self.test_module.insert.call(rs_data=instr, rs_entry_id=1)

        if instr["exec_fn"]["op_type"] == OpType.LOAD:
            yield from self.test_module.io_in.slave_wait()
            yield from self.test_module.io_in.slave_respond(1)
            yield Settle()
        v = yield from self.test_module.get_result.call()
        if instr["exec_fn"]["op_type"] == OpType.LOAD:
            self.assertEqual(v["result"], 1)

    def process(self):
        # just tests if FENCE doens't hang up the LSU
        load_fn = {"op_type": OpType.LOAD, "funct3": Funct3.W, "funct7": 0}
        fence_fn = {"op_type": OpType.FENCE, "funct3": 0, "funct7": 0}
        yield from self.push_one_instr(self.get_instr(load_fn))
        yield from self.push_one_instr(self.get_instr(fence_fn))
        yield from self.push_one_instr(self.get_instr(load_fn))

    def test_fence(self):
        self.gp = GenParams(test_core_config.replace(phys_regs_bits=3, rob_entries_bits=3))
        self.test_module = DummyLSUTestCircuit(self.gp)

        @def_method_mock(lambda: self.test_module.exception_report)
        def exception_consumer(arg):
            self.assertTrue(False)

        with self.run_simulation(self.test_module) as sim:
            sim.add_sync_process(self.process)
            sim.add_sync_process(exception_consumer)


class TestDummyLSUClear(TestCaseWithSimulator):
    def setUp(self):
        self.gp = GenParams(test_core_config)
        self.test_module = DummyLSUTestCircuit(self.gp)

    def generate_instr(self, *, is_store: bool = False, **kwargs):
        addr = (random.randrange(1, 2**self.gp.isa.xlen) // 4) * 4
        return {
            "rp_s1": 0,
            "rp_s2": 0,
            "rp_dst": 0,
            "rob_id": 0,
            "exec_fn": {"op_type": OpType.STORE if is_store else OpType.LOAD, "funct3": Funct3.W, "funct7": 0},
            "s1_val": addr,
            "s2_val": 0,
            "imm": 0,
        } | kwargs, addr >> 2

    def check_second_instr_liveness(self, m, is_store):
        yield from m.select.call()
        instr, addr = self.generate_instr(is_store=is_store)
        yield from m.insert.call(rs_data=instr, rs_entry_id=0)
        if is_store:
            yield from m.precommit.call(rob_id=0)
        yield from m.io_in.slave_wait()
        yield from m.io_in.slave_verify(exp_addr=addr, exp_data=0, exp_we=is_store, exp_sel=0xF)
        if not is_store:
            yield from m.io_in.slave_respond(data=0xCAFEBABE)
            self.assertEqual(0xCAFEBABE, (yield from m.get_result.call())["result"])

    def test_clear_before_bus_request(self):
        """
        Tests clear method when it's called before request was sent to the bus
        """

        @def_method_mock(lambda: self.test_module.exception_report)
        def exception_consumer(arg):
            self.assertTrue(False)

        def process():
            m = self.test_module
            for is_store in (False, True):
                # first instruction
                yield from m.select.call()
                # instruction that won't execute immediately since not all operands are ready
                instr, addr = self.generate_instr(is_store=is_store, rp_s1=1)
                yield from m.insert.call(rs_data=instr, rs_entry_id=0)
                yield from m.clear.call()

                self.check_second_instr_liveness(m, is_store)

        with self.run_simulation(self.test_module) as sim:
            sim.add_sync_process(process)
            sim.add_sync_process(exception_consumer)

    def test_clear_after_bus_request(self):
        """
        Test clear method when it's called after the bus request was sent,
        but before the response on the bus arrived.
        """

        @def_method_mock(lambda: self.test_module.exception_report)
        def exception_consumer(arg):
            self.assertTrue(False)

        def process():
            m = self.test_module
            for is_store in (False, True):
                # first instruction
                yield from m.select.call()
                instr, addr = self.generate_instr(is_store=is_store)
                yield from m.insert.call(rs_data=instr, rs_entry_id=0)
                if is_store:
                    yield from m.precommit.call(rob_id=0)
                yield from m.io_in.slave_wait()
                yield from m.io_in.slave_verify(exp_addr=addr, exp_data=0, exp_we=is_store, exp_sel=0xF)
                yield from m.clear.call()
                # needs some response regardless of being load/store
                yield from m.io_in.slave_respond(data=0xDEADBEEF)

                yield from self.check_second_instr_liveness(m, is_store)

        with self.run_simulation(self.test_module) as sim:
            sim.add_sync_process(process)
            sim.add_sync_process(exception_consumer)

    def test_clear_after_bus_response(self):
        """
        Test clear method when it's called after the bus request was sent
        and after response from the bus arrived, but wasn't read by
        get_result yet
        """

        @def_method_mock(lambda: self.test_module.exception_report)
        def exception_consumer(arg):
            self.assertTrue(False)

        def process():
            m = self.test_module
            for is_store in (False, True):
                # first instruction
                yield from m.select.call()
                instr, addr = self.generate_instr(is_store=is_store)
                yield from m.insert.call(rs_data=instr, rs_entry_id=0)
                if is_store:
                    yield from m.precommit.call(rob_id=0)
                yield from m.io_in.slave_wait()
                yield from m.io_in.slave_verify(exp_addr=addr, exp_data=0, exp_we=is_store, exp_sel=0xF)
                # needs some response regardless of being load/store
                yield from m.io_in.slave_respond(data=0xDEADBEEF)
                # wait for get_result to become ready before we call clear
                while (yield from m.get_result.call_try()) is None:
                    pass
                yield from m.clear.call()

                yield from self.check_second_instr_liveness(m, is_store)

        with self.run_simulation(self.test_module) as sim:
            sim.add_sync_process(process)
            sim.add_sync_process(exception_consumer)
