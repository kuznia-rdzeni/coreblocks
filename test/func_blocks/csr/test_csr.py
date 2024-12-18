from amaranth import *
import random

from transactron.lib import Adapter
from transactron.core.tmodule import TModule
from coreblocks.func_blocks.csr.csr import CSRUnit
from coreblocks.priv.csr.csr_register import CSRRegister
from coreblocks.priv.csr.csr_instances import GenericCSRRegisters
from coreblocks.params import GenParams
from coreblocks.arch import Funct3, ExceptionCause, OpType
from coreblocks.params.configurations import test_core_config
from coreblocks.interface.layouts import ExceptionRegisterLayouts, RetirementLayouts
from coreblocks.interface.keys import (
    AsyncInterruptInsertSignalKey,
    ExceptionReportKey,
    InstructionPrecommitKey,
    CSRInstancesKey,
)
from coreblocks.arch.isa_consts import PrivilegeLevel
from transactron.lib.adapters import AdapterTrans
from transactron.utils.dependencies import DependencyContext

from transactron.testing import *


class CSRUnitTestCircuit(Elaboratable):
    def __init__(self, gen_params: GenParams, csr_count: int, only_legal=True):
        self.gen_params = gen_params
        self.csr_count = csr_count
        self.only_legal = only_legal

    def elaborate(self, platform):
        m = Module()

        m.submodules.precommit = self.precommit = TestbenchIO(
            Adapter.create(
                i=self.gen_params.get(RetirementLayouts).precommit_in,
                o=self.gen_params.get(RetirementLayouts).precommit_out,
                nonexclusive=True,
                combiner=lambda m, args, runs: args[0],
            ).set(with_validate_arguments=True)
        )
        DependencyContext.get().add_dependency(InstructionPrecommitKey(), self.precommit.adapter.iface)

        m.submodules.dut = self.dut = CSRUnit(self.gen_params)

        m.submodules.select = self.select = TestbenchIO(AdapterTrans(self.dut.select))
        m.submodules.insert = self.insert = TestbenchIO(AdapterTrans(self.dut.insert))
        m.submodules.update = self.update = TestbenchIO(AdapterTrans(self.dut.update))
        m.submodules.accept = self.accept = TestbenchIO(AdapterTrans(self.dut.get_result))
        m.submodules.exception_report = self.exception_report = TestbenchIO(
            Adapter.create(i=self.gen_params.get(ExceptionRegisterLayouts).report)
        )
        m.submodules.csr_instances = self.csr_instances = GenericCSRRegisters(self.gen_params)
        m.submodules.priv_io = self.priv_io = TestbenchIO(AdapterTrans(self.csr_instances.m_mode.priv_mode.write))
        DependencyContext.get().add_dependency(ExceptionReportKey(), self.exception_report.adapter.iface)
        DependencyContext.get().add_dependency(AsyncInterruptInsertSignalKey(), Signal())
        DependencyContext.get().add_dependency(CSRInstancesKey(), self.csr_instances)

        m.submodules.fetch_resume = self.fetch_resume = TestbenchIO(AdapterTrans(self.dut.fetch_resume))

        self.csr = {}

        def make_csr(number: int):
            csr = CSRRegister(csr_number=number, gen_params=self.gen_params)
            self.csr[number] = csr
            m.submodules += csr

        # simple test not using external r/w functionality of csr
        for i in range(self.csr_count):
            make_csr(i)

        if not self.only_legal:
            make_csr(0xCC0)  # read-only csr
            make_csr(0x7FE)  # machine mode only

        return m


class TestCSRUnit(TestCaseWithSimulator):
    def gen_expected_out(self, sim: TestbenchContext, op: Funct3, rd: int, rs1: int, operand_val: int, csr: int):
        exp_read = {"rp_dst": rd, "result": sim.get(self.dut.csr[csr].value)}
        rs1_val = {"rp_s1": rs1, "value": operand_val}

        exp_write = {}
        if op == Funct3.CSRRW or op == Funct3.CSRRWI:
            exp_write = {"csr": csr, "value": operand_val}
        elif (op == Funct3.CSRRC and rs1) or op == Funct3.CSRRCI:
            exp_write = {"csr": csr, "value": exp_read["result"] & ~operand_val}
        elif (op == Funct3.CSRRS and rs1) or op == Funct3.CSRRSI:
            exp_write = {"csr": csr, "value": exp_read["result"] | operand_val}
        else:
            exp_write = {"csr": csr, "value": sim.get(self.dut.csr[csr].value)}

        return {"exp_read": exp_read, "exp_write": exp_write, "rs1": rs1_val}

    def generate_instruction(self, sim: TestbenchContext):
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
        imm = random.randint(0, 2**5 - 1)
        rs1_val = random.randint(0, 2**self.gen_params.isa.xlen - 1) if rs1 else 0
        operand_val = imm if imm_op else rs1_val
        csr = random.choice(list(self.dut.csr.keys()))

        exp = self.gen_expected_out(sim, op, rd, rs1, operand_val, csr)

        value_available = random.random() < 0.2

        return {
            "instr": {
                "exec_fn": {"op_type": OpType.CSR_IMM if imm_op else OpType.CSR_REG, "funct3": op, "funct7": 0},
                "rp_s1": 0 if value_available or imm_op else rs1,
                "rp_s1_reg": rs1,
                "s1_val": exp["rs1"]["value"] if value_available and not imm_op else 0,
                "rp_dst": rd,
                "imm": imm,
                "csr": csr,
            },
            "exp": exp,
        }

    async def process_test(self, sim: TestbenchContext):
        self.dut.fetch_resume.enable(sim)
        self.dut.exception_report.enable(sim)
        for _ in range(self.cycles):
            await self.random_wait_geom(sim)

            op = self.generate_instruction(sim)

            await self.dut.select.call(sim)

            await self.dut.insert.call(sim, rs_data=op["instr"])

            await self.random_wait_geom(sim)
            if op["exp"]["rs1"]["rp_s1"]:
                await self.dut.update.call(sim, reg_id=op["exp"]["rs1"]["rp_s1"], reg_val=op["exp"]["rs1"]["value"])

            await self.random_wait_geom(sim)
            # TODO: this is a hack, a real method mock should be used
            for _, r in self.dut.precommit.adapter.validators:  # type: ignore
                sim.set(r, 1)
            self.dut.precommit.call_init(sim, side_fx=1)  # TODO: sensible precommit handling

            await self.random_wait_geom(sim)
            res, resume_res = await CallTrigger(sim).call(self.dut.accept).sample(self.dut.fetch_resume).until_done()
            self.dut.precommit.disable(sim)

            assert res is not None and resume_res is not None
            assert res.rp_dst == op["exp"]["exp_read"]["rp_dst"]
            if op["exp"]["exp_read"]["rp_dst"]:
                assert res.result == op["exp"]["exp_read"]["result"]
            assert sim.get(self.dut.csr[op["exp"]["exp_write"]["csr"]].value) == op["exp"]["exp_write"]["value"]
            assert res.exception == 0

    def test_randomized(self):
        self.gen_params = GenParams(test_core_config)
        random.seed(8)

        self.cycles = 256
        self.csr_count = 16

        self.dut = CSRUnitTestCircuit(self.gen_params, self.csr_count)

        with self.run_simulation(self.dut) as sim:
            sim.add_testbench(self.process_test)

    exception_csr_numbers = [
        0xCC0,  # read_only
        0xFFF,  # nonexistent
        0x7FE,  # missing priv
    ]

    async def process_exception_test(self, sim: TestbenchContext):
        self.dut.fetch_resume.enable(sim)
        self.dut.exception_report.enable(sim)
        for csr in self.exception_csr_numbers:
            if csr == 0x7FE:
                await self.dut.priv_io.call(sim, data=PrivilegeLevel.USER)
            else:
                await self.dut.priv_io.call(sim, data=PrivilegeLevel.MACHINE)

            await self.random_wait_geom(sim)

            await self.dut.select.call(sim)

            rob_id = random.randrange(2**self.gen_params.rob_entries_bits)
            await self.dut.insert.call(
                sim,
                rs_data={
                    "exec_fn": {"op_type": OpType.CSR_REG, "funct3": Funct3.CSRRW, "funct7": 0},
                    "rp_s1": 0,
                    "rp_s1_reg": 1,
                    "s1_val": 1,
                    "rp_dst": 2,
                    "imm": 0,
                    "csr": csr,
                    "rob_id": rob_id,
                },
            )

            await self.random_wait_geom(sim)
            # TODO: this is a hack, a real method mock should be used
            for _, r in self.dut.precommit.adapter.validators:  # type: ignore
                sim.set(r, 1)
            self.dut.precommit.call_init(sim, side_fx=1)

            await self.random_wait_geom(sim)
            res, report = await CallTrigger(sim).call(self.dut.accept).sample(self.dut.exception_report).until_done()
            self.dut.precommit.disable(sim)

            assert res["exception"] == 1
            assert report is not None
            report_dict = data_const_to_dict(report)
            report_dict.pop("mtval")  # mtval tested in mtval.asm test
            assert {"rob_id": rob_id, "cause": ExceptionCause.ILLEGAL_INSTRUCTION, "pc": 0} == report_dict

    def test_exception(self):
        self.gen_params = GenParams(test_core_config)
        random.seed(9)

        self.dut = CSRUnitTestCircuit(self.gen_params, 0, only_legal=False)

        with self.run_simulation(self.dut) as sim:
            sim.add_testbench(self.process_exception_test)


class TestCSRRegister(TestCaseWithSimulator):
    async def randomized_process_test(self, sim: TestbenchContext):
        # always enabled
        self.dut.read.enable(sim)

        previous_data = 0
        for _ in range(self.cycles):
            write = False
            fu_write = False
            fu_read = False
            exp_write_data = None

            if random.random() < 0.9:
                write = True
                exp_write_data = random.randint(0, 2**self.gen_params.isa.xlen - 1)
                self.dut.write.call_init(sim, data=exp_write_data)

            if random.random() < 0.3:
                fu_write = True
                # fu_write has priority over csr write, but it doesn't overwrite ro bits
                write_arg = random.randint(0, 2**self.gen_params.isa.xlen - 1)
                exp_write_data = (write_arg & ~self.ro_mask) | (
                    (exp_write_data if exp_write_data is not None else previous_data) & self.ro_mask
                )
                self.dut._fu_write.call_init(sim, data=write_arg)

            if random.random() < 0.2:
                fu_read = True
                self.dut._fu_read.call_init(sim)

            await sim.tick()

            exp_read_data = exp_write_data if fu_write or write else previous_data

            if fu_read:  # in CSRUnit this call is called before write and returns previous result
                assert data_const_to_dict(self.dut._fu_read.get_call_result(sim)) == {"data": exp_read_data}

            assert data_const_to_dict(self.dut.read.get_call_result(sim)) == {
                "data": exp_read_data,
                "read": int(fu_read),
                "written": int(fu_write),
            }

            read_result = self.dut.read.get_call_result(sim)
            assert read_result is not None
            previous_data = read_result.data

            self.dut._fu_read.disable(sim)
            self.dut._fu_write.disable(sim)
            self.dut.write.disable(sim)

    def test_randomized(self):
        self.gen_params = GenParams(test_core_config)
        random.seed(42)

        self.cycles = 200
        self.ro_mask = 0b101

        self.dut = SimpleTestCircuit(CSRRegister(0, self.gen_params, ro_bits=self.ro_mask))

        with self.run_simulation(self.dut) as sim:
            sim.add_testbench(self.randomized_process_test)

    async def filtermap_process_test(self, sim: TestbenchContext):
        prev_value = 0
        for _ in range(50):
            input = random.randrange(0, 2**34)

            await self.dut._fu_write.call(sim, data=input)
            output = (await self.dut._fu_read.call(sim))["data"]

            expected = prev_value
            if input & 1:
                expected = input
                if input & 2:
                    expected += 3

                expected &= ~(2**32)

                expected <<= 1
                expected &= 2**34 - 1

            assert output == expected

            prev_value = output

    def test_filtermap(self):
        gen_params = GenParams(test_core_config)

        def write_filtermap(m: TModule, v: Value):
            res = Signal(34)
            write = Signal()
            m.d.comb += res.eq(v)
            with m.If(v & 1):
                m.d.comb += write.eq(1)
            with m.If(v & 2):
                m.d.comb += res.eq(v + 3)
            return (write, res)

        random.seed(4325)

        self.dut = SimpleTestCircuit(
            CSRRegister(
                None,
                gen_params,
                width=34,
                ro_bits=(1 << 32),
                fu_read_map=lambda _, v: v << 1,
                fu_write_filtermap=write_filtermap,
            ),
        )

        with self.run_simulation(self.dut) as sim:
            sim.add_testbench(self.filtermap_process_test)

    async def comb_process_test(self, sim: TestbenchContext):
        self.dut.read.enable(sim)
        self.dut.read_comb.enable(sim)
        self.dut._fu_read.enable(sim)

        self.dut._fu_write.call_init(sim, data=0xFFFF)
        while self.dut._fu_write.get_call_result(sim) is None:
            await sim.tick()
        assert self.dut.read_comb.get_call_result(sim).data == 0xFFFF
        assert self.dut._fu_read.get_call_result(sim).data == 0xAB
        await sim.tick()
        assert self.dut.read.get_call_result(sim)["data"] == 0xFFFB
        assert self.dut._fu_read.get_call_result(sim)["data"] == 0xFFFB
        await sim.tick()

        self.dut._fu_write.call_init(sim, data=0x0FFF)
        self.dut.write.call_init(sim, data=0xAAAA)
        while self.dut._fu_write.get_call_result(sim) is None or self.dut.write.get_call_result(sim) is None:
            await sim.tick()
        assert data_const_to_dict(self.dut.read_comb.get_call_result(sim)) == {"data": 0x0FFF, "read": 1, "written": 1}
        await sim.tick()
        assert self.dut._fu_read.get_call_result(sim).data == 0xAAAA
        await sim.tick()

        # single cycle
        self.dut._fu_write.call_init(sim, data=0x0BBB)
        while self.dut._fu_write.get_call_result(sim) is None:
            await sim.tick()
        update_val = self.dut.read_comb.get_call_result(sim).data | 0xD000
        self.dut.write.call_init(sim, data=update_val)
        while self.dut.write.get_call_result(sim) is None:
            await sim.tick()
        await sim.tick()
        assert self.dut._fu_read.get_call_result(sim).data == 0xDBBB

    def test_comb(self):
        gen_params = GenParams(test_core_config)

        random.seed(4326)

        self.dut = SimpleTestCircuit(CSRRegister(None, gen_params, ro_bits=0b1111, fu_write_priority=False, init=0xAB))

        with self.run_simulation(self.dut) as sim:
            sim.add_testbench(self.comb_process_test)
