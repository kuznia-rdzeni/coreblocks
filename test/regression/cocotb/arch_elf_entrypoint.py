import os
import cocotb

from test.regression.cocotb import CocotbSimulation
from test.regression.test_arch_regression import run_arch_elf


@cocotb.test
async def do_test(dut):
    await run_arch_elf(CocotbSimulation(dut), os.environ["TESTNAME"])
