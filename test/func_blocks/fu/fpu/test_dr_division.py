from coreblocks.func_blocks.fu.fpu.dr_division import *
from coreblocks.func_blocks.fu.fpu.qsf_tables import R4A2RED_PARAMS
from transactron.testing import *
from amaranth import *


# x = int("1011010011", 2)
# d = int("1110110011", 2)


class TestDRDivision(TestCaseWithSimulator):
    def test_manual(self):
        params = DrDivParams(iterations=5, op_width=10, result_width=14)
        drd = SimpleTestCircuit(DrDivModule(div_params=params, qsf_params=R4A2RED_PARAMS))

        async def tests(sim: TestbenchContext):
            input_dict = {}
            input_dict["x"] = 2**9
            input_dict["d"] = 2**9
            print(input_dict["x"])
            print(input_dict["d"])
            await drd.div_init.call(sim, input_dict)
            resp = await drd.div_result.call(sim)
            assert resp["result"] == (2 ** (10 + 2))
            assert resp["zero_rem"] == 1

        async def test_process(sim: TestbenchContext):
            await tests(sim)

        with self.run_simulation(drd) as sim:
            sim.add_testbench(test_process)
