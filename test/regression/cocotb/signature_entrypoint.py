import os
import sys
import cocotb
from pathlib import Path

top_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(top_dir))

from test.regression.cocotb import CocotbSimulation  # noqa: E402
from test.regression.signature import run_test  # noqa: E402


@cocotb.test()
async def do_test(dut):
    cocotb.logging.getLogger().setLevel(cocotb.logging.INFO)

    test_name = os.environ["TESTNAME"]
    if test_name is None:
        raise RuntimeError("No ELF file provided")

    output = os.environ["OUTPUT"]
    if output is None:
        output = test_name + ".signature"

    await run_test(CocotbSimulation(dut), test_name, output)
