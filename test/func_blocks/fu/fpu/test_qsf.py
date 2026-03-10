from coreblocks.func_blocks.fu.fpu.fpu_qsf import *
from coreblocks.func_blocks.fu.fpu.qsf_tables import *
from transactron.testing import *
from amaranth import *


class TestQSF(TestCaseWithSimulator):

    def test_manual(self):
        intervals = Radix4A2Red.INTERVALS
        bounds = Radix4A2Red.BOUNDS
        digits = Radix4A2Red.DIGITS
        params = QSFParams(residual_width=7, divisor_width=4, q_bits=2)
        qsf = SimpleTestCircuit(
            QSFModule(
                qsf_params=params,
                intervals=intervals,
                bounds=bounds,
                digits=digits,
            )
        )

        async def qsf_test(sim, intervals, bounds, digits):
            test_offset = 2
            residual_bits_lower_bound = bounds[0][0] - test_offset
            for i in range(0, len(intervals)):
                divisor_bits = intervals[i]
                for j in range(0, len(bounds[i])):
                    residual_bits_upper_bound = bounds[i][j]
                    for residual_bits in range(
                        residual_bits_lower_bound, residual_bits_upper_bound
                    ):
                        input_dict = {
                            "residual": residual_bits,
                            "divisor": divisor_bits,
                        }
                        resp = await qsf.qsf_request.call(sim, input_dict)
                        assert resp["sign"] == digits[j][0]
                        assert resp["q"] == digits[j][1]
                    residual_bits_lower_bound = residual_bits_upper_bound

        async def test_process(sim: TestbenchContext):
            await qsf_test(sim, intervals, bounds, digits)

        with self.run_simulation(qsf) as sim:
            sim.add_testbench(test_process)
