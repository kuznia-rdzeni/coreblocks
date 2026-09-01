from test.sim.cocotb import CocotbSimulation, generate_tests
from test.regression.test_regression import run_test
from test.regression.conftest import get_all_test_names


async def do_test(dut, test_name):
    await run_test(CocotbSimulation(dut), test_name)


generate_tests(do_test, list(get_all_test_names()))
