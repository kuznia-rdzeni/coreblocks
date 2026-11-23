from coreblocks.func_blocks.fu.fpu.otfu import *
from transactron.testing import *
from amaranth import *
from dataclasses import dataclass


@dataclass
class TCase:
    digit_seq: list[tuple[int, int]]
    results_f1: list[int]
    results_fm1: list[int]


class TestOTFCR2(TestCaseWithSimulator):

    def test_manual(self):
        params = OTFUParams(result_width=6)
        otfu = SimpleTestCircuit(
            OTFUModule(
                otfu_params=params,
            )
        )

        async def otfu_test(sim):
            test_cases = [
                TCase(
                    [(0, 1), (0, 1), (0, 1), (1, 1), (1, 1)],
                    [0b11110000, 0b11011000, 0b11001100, 0b11000110, 0b11001011],
                    [0b11110000, 0b00011000, 0b00101100, 0b00110110, 0b00110011],
                ),
                TCase(
                    [(1, 1), (1, 1), (0, 0), (0, 1), (0, 0)],
                    [0b11110000, 0b00011000, 0b00101100, 0b00101110, 0b00101011],
                    [0b11110000, 0b11011000, 0b11001100, 0b11001110, 0b11010011],
                ),
                TCase(
                    [(0, 0), (0, 1), (0, 0), (0, 0), (0, 0)],
                    [0b11110000, 0b11111000, 0b11101100, 0b11101110, 0b11101111],
                    [0b11110000, 0b11111000, 0b00001100, 0b00001110, 0b00001111],
                ),
                TCase(
                    [(0, 1), (0, 1), (0, 0), (0, 0), (1, 1)],
                    [0b11110000, 0b11011000, 0b11001100, 0b11001110, 0b11001111],
                    [0b11110000, 0b00011000, 0b00101100, 0b00101110, 0b00101111],
                ),
            ]
            for tc in test_cases:
                await otfu.otfu_reset.call(sim)
                for i, digit in enumerate(tc.digit_seq):
                    print(i)
                    resp = await otfu.otfu_result.call(sim)
                    assert resp["f_one"] == tc.results_f1[i]
                    assert resp["f_m_one"] == tc.results_fm1[i]
                    input_dict = {"sign": digit[0], "q": digit[1]}
                    await otfu.otfu_add_digit.call(sim, input_dict)

        async def test_process(sim: TestbenchContext):
            await otfu_test(sim)

        with self.run_simulation(otfu) as sim:
            sim.add_testbench(test_process)
