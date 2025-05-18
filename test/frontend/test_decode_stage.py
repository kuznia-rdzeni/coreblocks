from typing import Optional
import pytest
from transactron.lib import Adapter
from transactron.utils.amaranth_ext.elaboratables import ModuleConnector
from transactron.testing import (
    TestCaseWithSimulator,
    TestbenchIO,
    SimpleTestCircuit,
    TestbenchContext,
    data_const_to_dict,
)

from coreblocks.frontend.decoder.decode_stage import DecodeStage
from coreblocks.params import GenParams
from coreblocks.arch import OpType, Funct3, Funct7
from coreblocks.params.configurations import test_core_config


def mk_test(
    op_type: OpType,
    funct3: Funct3 = Funct3(0),
    funct7: Funct7 = Funct7(0),
    rl_dst: int = 0,
    rl_s1: int = 0,
    rl_s2: int = 0,
    imm: Optional[int] = None,
    csr: Optional[int] = None,
):
    return {
        "exec_fn": {"op_type": op_type, "funct3": funct3, "funct7": funct7},
        "regs_l": {"rl_dst": rl_dst, "rl_s1": rl_s1, "rl_s2": rl_s2},
        "imm": imm,
        "pc": 0,
        "csr": csr,
    }


tests = [
    (0x02A28213, 0, mk_test(op_type=OpType.ARITHMETIC, funct3=Funct3.ADD, rl_dst=4, rl_s1=5, imm=42, csr=42)),
    (
        0x003100B3,
        0,
        mk_test(op_type=OpType.ARITHMETIC, funct3=Funct3.ADD, funct7=Funct7.ADD, rl_dst=1, rl_s1=2, rl_s2=3),
    ),
    (0x00000000, 0, mk_test(op_type=OpType.EXCEPTION, funct3=Funct3._EILLEGALINSTR)),
    (0x02A28213, 1, mk_test(op_type=OpType.EXCEPTION, funct3=Funct3._EINSTRACCESSFAULT)),
]


class TestDecode(TestCaseWithSimulator):
    @pytest.fixture(autouse=True)
    def setup(self, fixture_initialize_testing_env):
        self.gen_params = GenParams(test_core_config.replace(start_pc=24))

        self.decode = DecodeStage(self.gen_params)

        self.push_raw = TestbenchIO(Adapter(self.decode.get_raw))
        self.get_decoded = TestbenchIO(Adapter(self.decode.push_decoded))

        self.m = SimpleTestCircuit(
            ModuleConnector(
                decode=self.decode,
                push_raw=self.push_raw,
                get_decoded=self.get_decoded,
            )
        )

    async def decode_input_proc(self, sim: TestbenchContext):
        for instr, access_fault, _ in tests:
            await self.push_raw.call(sim, instr=instr, access_fault=access_fault)

    async def decode_output_proc(self, sim: TestbenchContext):
        for _, _, data in tests:
            decoded = await self.get_decoded.call(sim)
            data = dict(data)
            if data["csr"] is None:
                data["csr"] = decoded.csr
            if data["imm"] is None:
                data["imm"] = decoded.imm
            assert data_const_to_dict(decoded) == data

    def test(self):
        with self.run_simulation(self.m) as sim:
            sim.add_testbench(self.decode_input_proc)
            sim.add_testbench(self.decode_output_proc)
