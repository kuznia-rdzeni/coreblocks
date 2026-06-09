import os
import sys
from pathlib import Path
import cocotb

top_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(top_dir))

from test.regression.cocotb import CocotbSimulation  # noqa: E402
from test.regression.test_arch_regression import run_arch_elf  # noqa: E402


@cocotb.test
async def do_test(dut):
    test_name = os.environ["TESTNAME"]
    if test_name == "SKIP":
        return
    await run_arch_elf(CocotbSimulation(dut), test_name)
