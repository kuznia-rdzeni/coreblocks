import os
import sys
from pathlib import Path

import cocotb

top_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(top_dir))

from test.regression.arch_elf import run_arch_elf  # noqa: E402
from test.regression.cocotb import CocotbSimulation  # noqa: E402


@cocotb.test()  # type: ignore
async def do_test(dut):
    elf_path = os.environ.get("TESTNAME")
    if not elf_path:
        raise RuntimeError("No ELF file provided")

    await run_arch_elf(CocotbSimulation(dut), elf_path)
