from .memory import *
from .common import SimulationBackend
from .conftest import riscv_tests_dir
from test.regression.pysim import PySimulation
import xml.etree.ElementTree as eT
import asyncio
from typing import Literal
import os
import pytest
import subprocess
import json
import tempfile
from filelock import FileLock

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
    arglist = ["make", "-C", "test/regression/cocotb", "-f", "test.Makefile"]
    arglist += [f"TESTCASE={test_name}"]

    verilog_code = os.path.join(os.getcwd(), "core.v")
    gen_info_path = f"{verilog_code}.json"
    arglist += [f"_COREBLOCKS_GEN_INFO={gen_info_path}"]
    arglist += [f"VERILOG_SOURCES={verilog_code}"]
    tmp_result_file = tempfile.NamedTemporaryFile("r")
    arglist += [f"COCOTB_RESULTS_FILE={tmp_result_file.name}"]

    if traces:
        arglist += ["TRACES=1"]

    res = subprocess.run(arglist)

    assert res.returncode == 0

    tree = eT.parse(tmp_result_file.name)
    assert len(list(tree.iter("failure"))) == 0


def regression_body_with_pysim(test_name: str, traces: bool, verbose: bool):
    traces_file = None
    if traces:
        traces_file = REGRESSION_TESTS_PREFIX + test_name
    asyncio.run(run_test(PySimulation(verbose, traces_file=traces_file), test_name))


@pytest.fixture(scope="session")
def verilate_model(worker_id, request: pytest.FixtureRequest):
    """
    Fixture to prevent races on verilating the coreblocks model. It is run only in
    distributed, cocotb, mode. It executes a 'SKIP' regression test which verilates the model.
    """
    if request.session.config.getoption("coreblocks_backend") != "cocotb" or worker_id == "master":
        # pytest expect yield on every path in fixture
        yield None
        return

    lock_path = "_coreblocks_regression.lock"
    counter_path = "_coreblocks_regression.counter"
    with FileLock(lock_path):
        regression_body_with_cocotb("SKIP", False)
        if os.path.exists(counter_path):
            with open(counter_path, "r") as counter_file:
                c = json.load(counter_file)
        else:
            c = 0
        with open(counter_path, "w") as counter_file:
            json.dump(c + 1, counter_file)
    yield
    # Session teardown
    deferred_remove = False
    with FileLock(lock_path):
        with open(counter_path, "r") as counter_file:
            c = json.load(counter_file)
        if c == 1:
            deferred_remove = True
        else:
            with open(counter_path, "w") as counter_file:
                json.dump(c - 1, counter_file)
    if deferred_remove:
        os.remove(lock_path)
        os.remove(counter_path)


def test_entrypoint(test_name: str, backend: Literal["pysim", "cocotb"], traces: bool, verbose: bool, verilate_model):
    if backend == "cocotb":
        regression_body_with_cocotb(test_name, traces)
    elif backend == "pysim":
        regression_body_with_pysim(test_name, traces, verbose)
