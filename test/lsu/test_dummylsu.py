import random
from collections import deque

from amaranth import Elaboratable, Module
from amaranth.sim import Settle, Passive

from coreblocks.params import GenParams
from coreblocks.transactions import TransactionModule
from coreblocks.transactions.lib import AdapterTrans
from coreblocks.lsu.dummyLsu import LSUDummy
from coreblocks.params.isa import *
from coreblocks.peripherals.wishbone import *
from test.common import TestbenchIO, TestCaseWithSimulator
from test.peripherals.test_wishbone import WishboneInterfaceWrapper


class DummyLSUTestCircuit(Elaboratable):
    def __init__(self, gen: GenParams):
        self.gen = gen

    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        wb_params = WishboneParameters(
            data_width=self.gen.isa.ilen,
            addr_width=32,
        )

        self.bus = WishboneMaster(wb_params)
        m.submodules.func_unit = func_unit = LSUDummy(self.gen, self.bus)

        m.submodules.select_mock = self.select = TestbenchIO(AdapterTrans(func_unit.select))
        m.submodules.insert_mock = self.insert = TestbenchIO(AdapterTrans(func_unit.insert))
        m.submodules.update_mock = self.update = TestbenchIO(AdapterTrans(func_unit.update))
        m.submodules.get_result_mock = self.get_result = TestbenchIO(AdapterTrans(func_unit.get_result))
        self.io_in = WishboneInterfaceWrapper(self.bus.wbMaster)
        m.submodules.bus = self.bus
        return tm


class TestDummyLSULoads(TestCaseWithSimulator):
    def generateInstr(self, max_reg_val, max_imm_val):
        ops = {
            "LB": (Opcode.LOAD, Funct3.B),  # lb
            "LBU": (Opcode.LOAD, Funct3.BU),  # lbu
            "LH": (Opcode.LOAD, Funct3.H),  # lh
            "LHU": (Opcode.LOAD, Funct3.HU),  # lhu
            "LW": (Opcode.LOAD, Funct3.W),  # lw
        }
        ops_k = list(ops.keys())
        for i in range(self.tests_number):
            # generate opcode
            op = ops[ops_k[random.randint(0, len(ops) - 1)]]
            exec_fn = {"op_type": op[0], "funct3": op[1], "funct7": 0}
            if op[1] == Funct3.B or op[1] == Funct3.BU:
                mask = 1
            elif op[1] == Funct3.H or op[1] == Funct3.HU:
                mask = 0x3
            else:
                mask = 0xF

            # generate rp1, val1 which create addr
            if random.randint(0, 1):
                rp_s1 = random.randint(1, 2**self.gp.phys_regs_bits - 1)
                s1_val = 0
                addr = random.randint(0, max_reg_val // 4) * 4
                self.announce_queue.append({"tag": rp_s1, "value": addr})
            else:
                rp_s1 = 0
                s1_val = random.randint(0, max_reg_val // 4) * 4
                addr = s1_val
                self.announce_queue.append(None)

            # generate imm
            if random.randint(0, 1):
                imm = 0
            else:
                imm = random.randint(0, max_imm_val // 4) * 4

            addr += imm
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
                {"addr": addr, "mask": mask, "rnd_bytes": bytes.fromhex(f"{random.randint(0,2**32-1):08x}")}
            )

    def setUp(self) -> None:
        random.seed(14)
        self.tests_number = 50
        self.gp = GenParams("rv32i", phys_regs_bits=3, rob_entries_bits=3)
        self.test_module = DummyLSUTestCircuit(self.gp)
        self.instr_queue = deque()
        self.announce_queue = deque()
        self.mem_data_queue = deque()
        self.returned_data = deque()
        self.generateInstr(2**7, 2**7)

    def random_wait(self):
        for i in range(random.randint(0, 10)):
            yield

    def wishbone_slave(self):
        yield Passive()

        while True:
            yield from self.test_module.io_in.slave_wait()
            generated_data = self.mem_data_queue.pop()

            mask = generated_data["mask"]
            # addr = yield self.test_module.io_in.wb.adr
            # self.assertEqual(addr, generated_data["addr"])
            yield from self.test_module.io_in.slave_verify(generated_data["addr"], 0, 0, mask)
            yield from self.random_wait()

            if mask == 0x1:
                data = generated_data["rnd_bytes"][:1]
            elif mask == 0x3:
                data = generated_data["rnd_bytes"][:2]
            else:
                data = generated_data["rnd_bytes"][:4]
            data = int(data.hex(), 16)
            self.returned_data.append(data)
            yield from self.test_module.io_in.slave_respond(data)
            yield Settle()

    def inserter(self):
        for i in range(self.tests_number):
            req = self.instr_queue.pop()
            ret = yield from self.test_module.select.call()
            self.assertEqual(ret["rs_entry_id"], 0)
            print("Instrukcja:",req)
            yield from self.test_module.insert.call({"rs_data": req, "rs_entry_id": 1})
            announc = self.announce_queue.pop()
            if announc is not None:
                yield from self.test_module.update.call(announc)
            yield from self.random_wait()

    def consumer(self):
        for i in range(self.tests_number):
            v = yield from self.test_module.get_result.call()
            print("Wynik:", v)
            self.assertEqual(v["result"], self.returned_data.pop())
            yield from self.random_wait()

    def test(self):
        with self.runSimulation(self.test_module) as sim:
            sim.add_sync_process(self.wishbone_slave)
            sim.add_sync_process(self.inserter)
            sim.add_sync_process(self.consumer)


class TestDummyLSULoadsCycles(TestCaseWithSimulator):
    def generateInstr(self, max_reg_val, max_imm_val):
        s1_val = random.randint(0, max_reg_val // 4) * 4
        imm = random.randint(0, max_imm_val // 4) * 4
        rp_dst = random.randint(0, 2**self.gp.phys_regs_bits - 1)
        rob_id = random.randint(0, 2**self.gp.rob_entries_bits - 1)

        exec_fn = {"op_type": Opcode.LOAD, "funct3": Funct3.W, "funct7": 0}
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

        wish_data = {"addr": s1_val + imm, "mask": 0xF, "rnd_bytes": bytes.fromhex(f"{random.randint(0,2**32-1):08x}")}
        return instr, wish_data

    def setUp(self) -> None:
        random.seed(14)
        self.gp = GenParams("rv32i", phys_regs_bits=3, rob_entries_bits=3)
        self.test_module = DummyLSUTestCircuit(self.gp)

    def oneInstrTest(self):
        instr, wish_data = self.generateInstr(2**7, 2**7)

        ret = yield from self.test_module.select.call()
        self.assertEqual(ret["rs_entry_id"], 0)
        yield from self.test_module.insert.call({"rs_data": instr, "rs_entry_id": 1})
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
        with self.runSimulation(self.test_module) as sim:
            sim.add_sync_process(self.oneInstrTest)
