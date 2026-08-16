from coreblocks.func_blocks.fu.fpu.dr_division import *
from coreblocks.func_blocks.fu.fpu.qsf_tables import R4A2RED_PARAMS
from transactron.testing import *
from amaranth import *
from dataclasses import dataclass


@dataclass
class TCase:
    x: int
    d: int
    result: int
    zero_rem: int


class TestDRDivision(TestCaseWithSimulator):
    def test_manual(self):
        params = DrDivParams(
            iterations=7,
            fractional_bits=10,
            result_fractional_bits=14,
        )
        drd = SimpleTestCircuit(DrDivModule(div_params=params, qsf_params=R4A2RED_PARAMS))

        async def tests(sim: TestbenchContext):
            input_dict = {}
            test_cases = [
                TCase(0b1000000000, 0b1000000000, 0b1000000000000, 1),
                TCase(
                    0b1001011010,
                    0b1101011101,
                    0b101100101111,
                    0,
                ),
                TCase(
                    0b1011010011,
                    0b1110110011,
                    0b110000110110,
                    0,
                ),
            ]
            for tc in test_cases:
                input_dict["x"] = tc.x
                input_dict["d"] = tc.d
                await drd.div_init.call(sim, input_dict)
                resp = await drd.div_result.call(sim)
                assert resp["result"] == tc.result
                assert resp["zero_rem"] == tc.zero_rem

        async def test_process(sim: TestbenchContext):
            await tests(sim)

        with self.run_simulation(drd) as sim:
            sim.add_testbench(test_process)
