from test.regression.cocotb import CocotbSimulation, generate_tests
from test.regression.benchmark import run_benchmark, get_all_benchmark_names


async def _do_benchmark(dut, benchmark_name):
    await run_benchmark(CocotbSimulation(dut), benchmark_name)


generate_tests(_do_benchmark, list(get_all_benchmark_names()))
