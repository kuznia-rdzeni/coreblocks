import sys
import cocotb
from pathlib import Path

top_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(top_dir))

from test.regression.cocotb import CocotbSimulation, generate_tests  # noqa: E402
from test.regression.benchmark import run_benchmark, get_all_benchmark_names  # noqa: E402


async def _do_benchmark(dut, benchmark_name):
    cocotb.logging.getLogger().setLevel(cocotb.logging.DEBUG)
    await run_benchmark(CocotbSimulation(dut), benchmark_name)


generate_tests(_do_benchmark, list(get_all_benchmark_names()))
