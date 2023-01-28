from amaranth import *

from coreblocks.params import GenParams
from coreblocks.structs_common.csr import CSRUnit
from coreblocks.params.isa import Funct3
from coreblocks.frontend.decoder import OpType
from coreblocks.transactions.lib import Adapter

from ..common import *

import random


class CSRUnitTestCircuit(Elaboratable):
    def __init__(self, gen_params):
        self.gen_params = gen_params

    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        self.rob_single_insn = Signal()

        m.submodules.fetch_continue = self.fetch_continue = TestbenchIO(Adapter(i=1, o=1))

        m.submodules.dut = self.dut = CSRUnit(self.gen_params, self.rob_single_insn, self.fetch_continue.adapter.iface)

        m.submodules.select = self.select = TestbenchIO(AdapterTrans(self.dut.select))
        m.submodules.insert = self.insert = TestbenchIO(AdapterTrans(self.dut.insert))
        m.submodules.update = self.update = TestbenchIO(AdapterTrans(self.dut.update))
        m.submodules.accept = self.accept = TestbenchIO(AdapterTrans(self.dut.accept))

        return tm


class TestCSRUnit(TestCaseWithSimulator):
    def gen_expected_out(self, op, rd, rs1, csr):
        exp_read = {"rp_dst": rd, "result": (yield self.dut.dut.regfile[csr])}
        rs1_val = {"rp_s1": rs1, "value": random.randint(0, 2**self.gp.isa.xlen - 1) if rs1 else 0}

        exp_write = {}
        if op == Funct3.CSRRW:
            exp_write = {"csr": csr, "value": rs1_val["value"]}
        elif op == Funct3.CSRRC and rs1:
            exp_write = {"csr": csr, "value": exp_read["result"] & ~rs1_val["value"]}
        elif op == Funct3.CSRRS and rs1:
            exp_write = {"csr": csr, "value": exp_read["result"] | rs1_val["value"]}
        else:
            exp_write = {"csr": csr, "value": (yield self.dut.dut.regfile[csr])}

        return {"exp_read": exp_read, "exp_write": exp_write, "rs1": rs1_val}

    def generate_instruction(self):
        ops = [
            Funct3.CSRRW,
            Funct3.CSRRC,
            Funct3.CSRRS,
        ]

        op = random.choice(ops)
        rd = random.randint(0, 2**self.gp.phys_regs_bits - 1)
        rs1 = random.randint(0, 2**self.gp.phys_regs_bits - 1)
        csr = random.randint(0, 16)

        exp = yield from self.gen_expected_out(op, rd, rs1, csr)

        return {
            "instr": {
                "exec_fn": {"op_type": OpType.CSR, "funct3": op, "funct7": 0},
                "rp_s1": rs1,
                "rp_dst": rd,
                "csr": csr,
            },
            "exp": exp,
        }

    def process_test(self):
        yield from self.dut.fetch_continue.enable()
        for _ in range(self.cycles):
            while random.random() < 0.5:
                yield

            yield self.dut.rob_single_insn.eq(0)

            op = yield from self.generate_instruction()

            yield from self.dut.select.call()
            yield from self.dut.insert.call({"rs_data": op["instr"]})

            yield from self.dut.update.call({"tag": op["exp"]["rs1"]["rp_s1"], "value": op["exp"]["rs1"]["value"]})
            yield self.dut.rob_single_insn.eq(1)

            res = yield from self.dut.accept.call()

            self.assertTrue(self.dut.fetch_continue.done())
            self.assertEqual(res["rp_dst"], op["exp"]["exp_read"]["rp_dst"])
            if op["exp"]["exp_read"]["rp_dst"]:
                self.assertEqual(res["result"], op["exp"]["exp_read"]["result"])
            self.assertEqual(
                (yield self.dut.dut.regfile[op["exp"]["exp_write"]["csr"]]), op["exp"]["exp_write"]["value"]
            )

    def test_randomized(self):
        self.gp = GenParams("rv32i")
        self.dut = CSRUnitTestCircuit(self.gp)
        self.cycles = 1000

        with self.run_simulation(self.dut) as sim:
            sim.add_sync_process(self.process_test)
