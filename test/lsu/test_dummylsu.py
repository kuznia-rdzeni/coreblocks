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
from test.common import TestbenchIO, TestCaseWithSimulator, int_to_signed, signed_to_int
from test.peripherals.test_wishbone import WishboneInterfaceWrapper


def generateRegister(max_reg_val, phys_regs_bits):
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
        m.submodules.commit_mock = self.commit = TestbenchIO(AdapterTrans(func_unit.commit))
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
        def checkInstr(addr, op):
            rest = addr % 4
            if op[1] in {Funct3.B, Funct3.BU}:
                return True
            if op[1] in {Funct3.H, Funct3.HU} and rest in {0,2}:
                return True
            if op[1] == Funct3.W and rest == 0:
                return True
            return False
        def generateRandomOp():
            op = ops[ops_k[random.randint(0, len(ops) - 1)]]
            signess = False
            if op[1] == Funct3.B:
                mask = 1
                signess = True
            elif op[1] == Funct3.BU:
                mask = 1
            elif op[1] == Funct3.H:
                mask = 0x3
                signess = True
            elif op[1] == Funct3.HU:
                mask = 0x3
            else:
                mask = 0xF
            return (op, mask, signess)

        def generateImm():
            if random.randint(0, 1):
                return 0
            else:
                return random.randint(0, max_imm_val)

        def shiftMaskBasedOnAddr(mask, addr):
            rest = addr % 4
            if mask == 0x1:
                mask = mask << rest
            elif mask == 0x3:
                mask = mask << rest
            return mask

        for i in range(self.tests_number):
            generation_status = False
            while(not generation_status):
                # generate opcode
                (op, mask, signess) = generateRandomOp()
                # generate rp1, val1 which create addr
                rp_s1, s1_val, ann_data, addr = generateRegister(max_reg_val, self.gp.phys_regs_bits)
                # generate imm
                imm = generateImm()
                addr += imm
                generation_status = checkInstr(addr, op)
            
            self.announce_queue.append(ann_data)
            exec_fn = {"op_type": op[0], "funct3": op[1], "funct7": 0}

            mask = shiftMaskBasedOnAddr(mask, addr)

            #calculate aligned address
            rest = addr % 4
            addr = addr - rest


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
                {"addr": addr, "mask": mask, "sign": signess, "rnd_bytes": bytes.fromhex(f"{random.randint(0,2**32-1):08x}")}
            )

    def setUp(self) -> None:
        random.seed(14)
        self.tests_number = 100
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

            print("Generated data:", generated_data)
            mask = generated_data["mask"]
            sign = generated_data["sign"]
            # addr = yield self.test_module.io_in.wb.adr
            # self.assertEqual(addr, generated_data["addr"])
            yield from self.test_module.io_in.slave_verify(generated_data["addr"], 0, 0, mask)
            yield from self.random_wait()

            resp_data=int((generated_data["rnd_bytes"][:4]).hex(),16)
            if mask == 0x1:
                size=8
                data = resp_data & 0xFF
            elif mask == 0x2:
                size=8
                data = (resp_data >> 8) & 0xFF
            elif mask == 0x4:
                size=8
                data = (resp_data >> 16) & 0xFF
            elif mask == 0x8:
                size=8
                data = (resp_data >> 24) & 0xFF
            elif mask == 0x3:
                size=16
                data = resp_data & 0xFFFF
            elif mask == 0xc:
                size=16
                data = (resp_data >> 16) & 0xFFFF
            elif mask == 0xF:
                size=32
                data = resp_data & 0xFFFFFFFF
            else:
                raise RuntimeError("Unexpected mask")
            print("Data przed sign", data)
            if sign:
                data = int_to_signed(signed_to_int(data, size),32)
            print("Data po sign", data)
            self.returned_data.append(data)
            yield from self.test_module.io_in.slave_respond(resp_data)
            yield Settle()

    def inserter(self):
        for i in range(self.tests_number):
            req = self.instr_queue.pop()
            print("Instr:",req)
            ret = yield from self.test_module.select.call()
            self.assertEqual(ret["rs_entry_id"], 0)
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
        with self.run_simulation(self.test_module) as sim:
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
        with self.run_simulation(self.test_module) as sim:
            sim.add_sync_process(self.oneInstrTest)


class TestDummyLSUStores(TestCaseWithSimulator):
    def generateInstr(self, max_reg_val, max_imm_val):
        ops = {
            "SB": (Opcode.STORE, Funct3.B),
            "SH": (Opcode.STORE, Funct3.H),
            "SW": (Opcode.STORE, Funct3.W),
        }
        ops_k = list(ops.keys())
        for i in range(self.tests_number):
            # generate opcode
            op = ops[ops_k[random.randint(0, len(ops) - 1)]]
            exec_fn = {"op_type": op[0], "funct3": op[1], "funct7": 0}
            if op[1] == Funct3.B:
                mask = 1
            elif op[1] == Funct3.H:
                mask = 0x3
            else:
                mask = 0xF

            rp_s1, s1_val, ann_data1, addr = generateRegister(max_reg_val, self.gp.phys_regs_bits)
            rp_s2, s2_val, ann_data2, data = generateRegister(max_reg_val, self.gp.phys_regs_bits)
            if rp_s1 == rp_s2 and ann_data1 is not None and ann_data2 is not None:
                ann_data2 = None
                data = addr
            # decide in which order we would get announcments
            if random.randint(0, 1):
                self.announce_queue.append((ann_data1, ann_data2))
            else:
                self.announce_queue.append((ann_data2, ann_data1))

            # generate imm
            if random.randint(0, 1):
                imm = 0
            else:
                imm = random.randint(0, max_imm_val // 4) * 4

            addr += imm
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
        self.tests_number = 50
        self.gp = GenParams("rv32i", phys_regs_bits=3, rob_entries_bits=3)
        self.test_module = DummyLSUTestCircuit(self.gp)
        self.instr_queue = deque()
        self.announce_queue = deque()
        self.mem_data_queue = deque()
        self.get_result_data = deque()
        self.commit_data = deque()
        self.generateInstr(2**7, 2**7)

    def random_wait(self):
        for i in range(random.randint(0, 8)):
            yield

    def wishbone_slave(self):
        for i in range(self.tests_number):
            yield from self.test_module.io_in.slave_wait()
            generated_data = self.mem_data_queue.pop()

            mask = generated_data["mask"]
            if mask == 0x1:
                data = generated_data["data"][-1:]
            elif mask == 0x3:
                data = generated_data["data"][-2:]
            else:
                data = generated_data["data"][-4:]
            data = int(data.hex(), 16)
            yield from self.test_module.io_in.slave_verify(generated_data["addr"], data, 1, mask)
            yield from self.random_wait()

            yield from self.test_module.io_in.slave_respond(0)
            yield Settle()

    def inserter(self):
        for i in range(self.tests_number):
            req = self.instr_queue.pop()
            self.get_result_data.appendleft(req["rob_id"])
            ret = yield from self.test_module.select.call()
            self.assertEqual(ret["rs_entry_id"], 1)
            yield from self.test_module.insert.call({"rs_data": req, "rs_entry_id": 1})
            announc = self.announce_queue.pop()
            for j in range(2):
                if announc[j] is not None:
                    yield from self.random_wait()
                    yield from self.test_module.update.call(announc[j])
            yield from self.random_wait()

    def getResulter(self):
        for i in range(self.tests_number):
            v = yield from self.test_module.get_result.call()
            rob_id = self.get_result_data.pop()
            self.commit_data.appendleft(rob_id)
            self.assertEqual(v["rob_id"], rob_id)
            self.assertEqual(v["rp_dst"], 0)
            yield from self.random_wait()

    def commiter(self):
        for i in range(self.tests_number):
            while len(self.commit_data) == 0:
                yield
            rob_id = self.commit_data.pop()
            yield from self.test_module.commit.call({"rob_id": rob_id})

    def test(self):
        with self.run_simulation(self.test_module) as sim:
            sim.add_sync_process(self.wishbone_slave)
            sim.add_sync_process(self.inserter)
            sim.add_sync_process(self.getResulter)
            sim.add_sync_process(self.commiter)
