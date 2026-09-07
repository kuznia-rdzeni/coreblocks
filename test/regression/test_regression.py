from test.sim.memory import *
from test.sim.common import SimulationBackend
from .conftest import riscv_tests_dir, profile_dir, evlog_dir
from test.sim.cocotb import run_cocotb_entrypoint
from test.sim.pysim import PySimulation
import asyncio
from collections.abc import Callable
from typing import Literal
import os
import pytest

REGRESSION_TESTS_PREFIX = "test.regression."


# disable write protection for specific tests with writes to .text section
exclude_write_protection = ["rv32uc-rvc"]

# force executable bit for memory segments in specific tests
force_executable_memory = ["rv32ui-fence_i"]


class MMIO(MMIOSegment):
    def __init__(self, on_finish: Callable[[], None]):
        super().__init__(range(0xF0000000, 0xF0000000 + 4), SegmentFlags.READ | SegmentFlags.WRITE)
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
        force_executable=test_name in force_executable_memory,
    )
    mem_segments.append(mmio)

    mem_model = CoreMemoryModel(mem_segments)

    result = await sim_backend.run(mem_model, timeout_cycles=5000)

    if result.profile is not None:
        os.makedirs(profile_dir, exist_ok=True)
        result.profile.encode(f"{profile_dir}/test.regression.{test_name}.json")

    if result.evlog is not None:
        os.makedirs(evlog_dir, exist_ok=True)
        result.evlog.save(f"{evlog_dir}/test.regression.{test_name}.jsonl")

    if not result.success:
        raise RuntimeError("Simulation timed out")

    if mmio.failed_test:
        raise RuntimeError("Failing test: %d" % mmio.failed_test)


def regression_body_with_cocotb(test_name: str, traces: bool):
    assert run_cocotb_entrypoint(
        "test_entrypoint",
        traces=traces,
        additional_args=[f"TESTCASE={test_name}"],
    )


def regression_body_with_pysim(test_name: str, traces: bool):
    traces_file = None
    if traces:
        traces_file = REGRESSION_TESTS_PREFIX + test_name
    asyncio.run(run_test(PySimulation(traces_file=traces_file), test_name))


@pytest.fixture
def sim_backend(request: pytest.FixtureRequest):
    return request.config.getoption("coreblocks_backend")


@pytest.fixture
def traces_enabled(request: pytest.FixtureRequest):
    return request.config.getoption("coreblocks_traces")


def test_entrypoint(test_name: str, sim_backend: Literal["pysim", "cocotb"], traces_enabled: bool):
    if sim_backend == "cocotb":
        regression_body_with_cocotb(test_name, traces_enabled)
    elif sim_backend == "pysim":
        regression_body_with_pysim(test_name, traces_enabled)
