from amaranth import *

from coreblocks.structs_common.csr import CSRUnit, CSRRegister
from coreblocks.params.isa import Funct3
from coreblocks.frontend.decoder import OpType
from coreblocks.transactions.lib import Adapter

from ..common import *

import random


class CSRUnitTestCircuit(Elaboratable):
    def __init__(self, gen_params, csr_count):
        self.gen_params = gen_params
        self.csr_count = csr_count

    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        self.rob_single_insn = Signal()

        m.submodules.fetch_continue = self.fetch_continue = TestbenchIO(Adapter())

        m.submodules.dut = self.dut = CSRUnit(self.gen_params, self.rob_single_insn, self.fetch_continue.adapter.iface)

        m.submodules.select = self.select = TestbenchIO(AdapterTrans(self.dut.select))
        m.submodules.insert = self.insert = TestbenchIO(AdapterTrans(self.dut.insert))
        m.submodules.update = self.update = TestbenchIO(AdapterTrans(self.dut.update))
        m.submodules.accept = self.accept = TestbenchIO(AdapterTrans(self.dut.accept))

        self.csr = {}

        # simple test not using external r/w functionality of csr
        for i in range(self.csr_count):
            csr = CSRRegister(csr_number=i, gen_params=self.gen_params)
            self.dut.register(csr)
            self.csr[i] = csr
            m.submodules += csr

        return tm


class TestCSRUnit(TestCaseWithSimulator):
    def gen_expected_out(self, op, rd, rs1, operand_val, csr):
        exp_read = {"rp_dst": rd, "result": (yield self.dut.csr[csr].value)}
        rs1_val = {"rp_s1": rs1, "value": operand_val}

        exp_write = {}
        if op == Funct3.CSRRW or op == Funct3.CSRRWI:
            exp_write = {"csr": csr, "value": operand_val}
        elif (op == Funct3.CSRRC and rs1) or op == Funct3.CSRRCI:
            exp_write = {"csr": csr, "value": exp_read["result"] & ~operand_val}
        elif (op == Funct3.CSRRS and rs1) or op == Funct3.CSRRSI:
            exp_write = {"csr": csr, "value": exp_read["result"] | operand_val}
        else:
            exp_write = {"csr": csr, "value": (yield self.dut.csr[csr].value)}

        return {"exp_read": exp_read, "exp_write": exp_write, "rs1": rs1_val}

    def generate_instruction(self):
        ops = [
            Funct3.CSRRW,
            Funct3.CSRRC,
            Funct3.CSRRS,
            Funct3.CSRRWI,
            Funct3.CSRRCI,
            Funct3.CSRRSI,
        ]

        op = random.choice(ops)
        imm_op = op == Funct3.CSRRWI or op == Funct3.CSRRCI or op == Funct3.CSRRSI

        rd = random.randint(0, 15)
        rs1 = 0 if imm_op else random.randint(0, 15)
        imm = random.randint(0, 2**self.gp.isa.xlen - 1)
        rs1_val = random.randint(0, 2**self.gp.isa.xlen - 1) if rs1 else 0
        operand_val = imm if imm_op else rs1_val
        csr = random.randint(0, self.csr_count - 1)

        exp = yield from self.gen_expected_out(op, rd, rs1, operand_val, csr)

        value_available = random.random() < 0.2

        return {
            "instr": {
                "exec_fn": {"op_type": OpType.CSR, "funct3": op, "funct7": 0},
                "rp_s1": 0 if value_available or imm_op else rs1,
                "rp_s1_reg": rs1,
                "s1_val": exp["rs1"]["value"] if value_available and not imm_op else 0,
                "rp_dst": rd,
                "imm": imm,
                "csr": csr,
            },
            "exp": exp,
        }

    def random_wait(self, prob: float = 0.5):
        while random.random() < prob:
            yield

    def process_test(self):
        yield from self.dut.fetch_continue.enable()
        for _ in range(self.cycles):

            yield from self.random_wait()
            yield self.dut.rob_single_insn.eq(0)

            op = yield from self.generate_instruction()

            yield from self.dut.select.call()

            yield from self.dut.insert.call(rs_data=op["instr"])

            yield from self.random_wait()
            if op["exp"]["rs1"]["rp_s1"]:
                yield from self.dut.update.call(tag=op["exp"]["rs1"]["rp_s1"], value=op["exp"]["rs1"]["value"])

            yield from self.random_wait()
            yield self.dut.rob_single_insn.eq(1)

            yield from self.random_wait()
            res = yield from self.dut.accept.call()

            self.assertTrue(self.dut.fetch_continue.done())
            self.assertEqual(res["rp_dst"], op["exp"]["exp_read"]["rp_dst"])
            if op["exp"]["exp_read"]["rp_dst"]:
                self.assertEqual(res["result"], op["exp"]["exp_read"]["result"])
            self.assertEqual((yield self.dut.csr[op["exp"]["exp_write"]["csr"]].value), op["exp"]["exp_write"]["value"])

    def test_randomized(self):
        self.gp = test_gen_params("rv32i")
        random.seed(8)

        self.cycles = 256
        self.csr_count = 16

        self.dut = CSRUnitTestCircuit(self.gp, self.csr_count)

        with self.run_simulation(self.dut) as sim:
            sim.add_sync_process(self.process_test)


class TestCSRRegister(TestCaseWithSimulator):
    def process_test(self):
        # always enabled
        yield from self.dut.read.enable()

        previous_data = 0
        for _ in range(self.cycles):
            write = False
            fu_write = False
            fu_read = False
            exp_write_data = None

            if random.random() < 0.9:
                write = True
                exp_write_data = random.randint(0, 2**self.gp.isa.xlen - 1)
                yield from self.dut.write.call_init(data=exp_write_data)

            if random.random() < 0.3:
                fu_write = True
                # fu_write has priority over csr write, but it doesn't overwrite ro bits
                write_arg = random.randint(0, 2**self.gp.isa.xlen - 1)
                exp_write_data = (write_arg & ~self.ro_mask) | (
                    (exp_write_data if exp_write_data is not None else previous_data) & self.ro_mask
                )
                yield from self.dut._fu_write.call_init(data=write_arg)

            if random.random() < 0.2:
                fu_read = True
                yield from self.dut._fu_read.enable()

            yield
            yield Settle()

            exp_read_data = exp_write_data if fu_write or write else previous_data

            if fu_read:  # in CSRUnit this call is called before write and returns previous result
                self.assertEqual((yield from self.dut._fu_read.call_result()), {"data": exp_read_data})

            self.assertEqual(
                (yield from self.dut.read.call_result()),
                {
                    "data": exp_read_data,
                    "read": int(fu_read),
                    "written": int(fu_write),
                },
            )

            read_result = yield from self.dut.read.call_result()
            self.assertIsNotNone(read_result)
            previous_data = read_result["data"]  # type: ignore

            yield from self.dut._fu_read.disable()
            yield from self.dut._fu_write.disable()
            yield from self.dut.write.disable()

    def test_randomized(self):
        self.gp = test_gen_params("rv32i")
        random.seed(42)

        self.cycles = 200
        self.ro_mask = 0b101

        self.dut = SimpleTestCircuit(CSRRegister(0, self.gp, ro_bits=self.ro_mask))

        with self.run_simulation(self.dut) as sim:
            sim.add_sync_process(self.process_test)
