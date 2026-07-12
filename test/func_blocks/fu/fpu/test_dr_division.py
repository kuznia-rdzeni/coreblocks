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
        params = DrDivParams(iterations=5, op_width=10, result_width=14)
        drd = SimpleTestCircuit(DrDivModule(div_params=params, qsf_params=R4A2RED_PARAMS))

        async def tests(sim: TestbenchContext):
            input_dict = {}
            test_cases = [
                TCase(2**9, 2**9, 2**12, 1),
                TCase(
                    int("1001011010", 2),
                    int("1101011101", 2),
                    int("101100101111", 2),
                    0,
                ),
                TCase(int("1011010011"), int("1110110011", 2), int("110000110110", 2), 0),
            ]
            for tc in test_cases:
                input_dict["x"] = tc["x"]
                input_dict["d"] = tc["d"]
                print("TC")
                print(input_dict["x"])
                print(input_dict["d"])
                await drd.div_init.call(sim, input_dict)
                resp = await drd.div_result.call(sim)
                assert resp["result"] == tc["result"]
                assert resp["zero_rem"] == tc["zero_rem"]

        async def test_process(sim: TestbenchContext):
            await tests(sim)

        with self.run_simulation(drd) as sim:
            sim.add_testbench(test_process)
