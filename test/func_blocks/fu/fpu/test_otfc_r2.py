from coreblocks.func_blocks.fu.fpu.otfc import *
from transactron.testing import *
from amaranth import *
from dataclasses import dataclass


@dataclass
class TCase:
    digit_seq: list[tuple[int, int]]
    result: int


class TestOTFCR2(TestCaseWithSimulator):

    def test_manual(self):
        params = OTFCParams(result_width=12, digit_width=DigitWidth.WIDTH_ONE)
        otfc = SimpleTestCircuit(
            OTFCModule(
                otfc_params=params,
            )
        )

        async def otfc_test(sim):
            test_cases = [
                TCase(
                    [
                        (0, 0),
                        (0, 1),
                        (0, 0),
                        (0, 0),
                        (0, 0),
                        (0, 0),
                        (0, 0),
                        (1, 1),
                        (1, 1),
                        (0, 0),
                        (0, 1),
                        (0, 0),
                    ],
                    1002,
                ),
                TCase(
                    [
                        (0, 0),
                        (0, 0),
                        (0, 0),
                        (0, 0),
                        (0, 0),
                        (0, 0),
                        (0, 1),
                        (0, 0),
                        (1, 1),
                        (0, 0),
                        (0, 0),
                        (1, 1),
                    ],
                    23,
                ),
                TCase(
                    [
                        (1, 1),
                        (0, 0),
                        (1, 1),
                        (0, 0),
                        (0, 0),
                        (0, 0),
                        (0, 0),
                        (0, 1),
                        (0, 0),
                        (0, 1),
                        (0, 0),
                        (0, 1),
                    ],
                    1557 + (1 << 12),
                ),
                TCase(
                    [
                        (0, 0),
                        (0, 0),
                        (0, 0),
                        (0, 0),
                        (0, 0),
                        (0, 0),
                        (0, 0),
                        (0, 0),
                        (0, 0),
                        (1, 1),
                        (0, 0),
                        (0, 1),
                    ],
                    4093 + (1 << 12),
                ),
                TCase(
                    [
                        (0, 1),
                        (0, 0),
                        (0, 0),
                        (0, 0),
                        (0, 0),
                        (0, 0),
                        (0, 0),
                        (0, 0),
                        (0, 0),
                        (0, 1),
                        (0, 0),
                        (0, 0),
                    ],
                    (1 << 11) + (1 << 2),
                ),
                TCase(
                    [
                        (0, 0),
                        (0, 0),
                        (0, 0),
                        (0, 0),
                        (0, 0),
                        (0, 0),
                        (0, 0),
                        (0, 0),
                        (0, 0),
                        (0, 0),
                        (0, 0),
                        (0, 0),
                    ],
                    0,
                ),
            ]
            for tc in test_cases:
                await otfc.otfc_reset.call(sim)
                for digit in tc.digit_seq:
                    input_dict = {"sign": digit[0], "q": digit[1]}
                    await otfc.otfc_add_digit.call(sim, input_dict)
                resp = await otfc.otfc_result.call(sim, {"shift": 0})
                assert resp["result"] == tc.result

            zero_termination_case = TCase([(1, 1), (0, 0), (0, 0), (0, 1), (0, 1), (0, 0)], 6528)
            for digit in zero_termination_case.digit_seq:
                input_dict = {"sign": digit[0], "q": digit[1]}
                await otfc.otfc_add_digit.call(sim, input_dict)
            resp = await otfc.otfc_result.call(sim, {"shift": 2 * 3})
            assert resp["result"] == zero_termination_case.result

        async def test_process(sim: TestbenchContext):
            await otfc_test(sim)

        with self.run_simulation(otfc) as sim:
            sim.add_testbench(test_process)
