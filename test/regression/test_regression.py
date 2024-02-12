from .memory import *
from .common import SimulationBackend
from .conftest import riscv_tests_dir
from test.regression.pysim import PySimulation
import asyncio
from typing import Literal
import os
import subprocess
import sys

REGRESSION_TESTS_PREFIX = "test.regression."


# disable write protection for specific tests with writes to .text section
exclude_write_protection = ["rv32uc-rvc"]


class MMIO(MemorySegment):
    def __init__(self, on_finish: Callable[[], None]):
        super().__init__(range(0x80000000, 0x80000000 + 4), SegmentFlags.READ | SegmentFlags.WRITE)
        self.on_finish = on_finish
        self.failed_test = 0

    def read(self, req: ReadRequest) -> ReadReply:
        return ReadReply()

    def write(self, req: WriteRequest) -> WriteReply:
        self.failed_test = req.data
        self.on_finish()
        return WriteReply()


async def run_test(sim_backend: SimulationBackend, test_name: str):
    mmio = MMIO(lambda: sim_backend.stop())

    mem_segments: list[MemorySegment] = []
    mem_segments += load_segments_from_elf(
        str(riscv_tests_dir.joinpath("test-" + test_name)),
        disable_write_protection=test_name in exclude_write_protection,
    )
    mem_segments.append(mmio)

    mem_model = CoreMemoryModel(mem_segments)

    result = await sim_backend.run(mem_model, timeout_cycles=5000)

    if not result.success:
        raise RuntimeError("Simulation timed out")

    if mmio.failed_test:
        raise RuntimeError("Failing test: %d" % mmio.failed_test)


def regression_body_with_cocotb(test_name: str, traces: bool):
    print(os.getcwd(), file=sys.stderr)
    arglist = ["make", "-C", "cocotb", "-f", "test.Makefile"]
    arglist += [f"TESTCASE={test_name}"]

    if traces:
        arglist += ["TRACES=1"]

    res = subprocess.run(arglist)

    assert res.returncode == 0


def regression_body_with_pysim(test_name: str, traces: bool, verbose: bool):
    traces_file = None
    if traces:
        traces_file = REGRESSION_TESTS_PREFIX + test_name
    asyncio.run(run_test(PySimulation(verbose, traces_file=traces_file), test_name))


def test_entrypoint(test_name: str, backend: Literal["pysim", "cocotb"], traces: bool, verbose: bool):
    if backend == "cocotb":
        regression_body_with_cocotb(test_name, traces)
    elif backend == "pysim":
        regression_body_with_pysim(test_name, traces, verbose)
