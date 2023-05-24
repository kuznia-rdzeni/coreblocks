import sys
import cocotb
from pathlib import Path

top_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(top_dir))

from test.regression.cocotb import CocotbSimulation, generate_tests  # noqa: E402
from test.regression.test import run_test, get_all_test_names  # noqa: E402


async def do_test(dut, test_name):
    cocotb.logging.getLogger().setLevel(cocotb.logging.INFO)
    await run_test(CocotbSimulation(dut), test_name)


generate_tests(do_test, list(get_all_test_names()))
