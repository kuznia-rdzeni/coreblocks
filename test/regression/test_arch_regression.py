from typing import Literal
from pathlib import Path
from filelock import FileLock
import pytest
import argparse
import os
import re
import subprocess
import sys
import tempfile
import asyncio
import xml.etree.ElementTree as eT

from .conftest import arch_tests_dir
from .pysim import PySimulation
from .memory import (
    CoreMemoryModel,
    MemorySegment,
    ReadReply,
    ReadRequest,
    ReplyStatus,
    SegmentFlags,
    WriteReply,
    WriteRequest,
    load_segments_from_elf,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_ROOT = Path(__file__).resolve().parent / "cocotb" / "build" / "riscv-arch-test"
TEST_ROOT = Path(__file__).resolve().parent / "cocotb"

VERILOG_LOCK_FILE = BUILD_ROOT / "verilog.lock"
VERILOG_STAMP = BUILD_ROOT / "verilog.built"
VERILOG_ROOT = BUILD_ROOT / "verilog"

BUILT_LOCK_FILE = BUILD_ROOT / "cocotb.lock"

CORE_V = VERILOG_ROOT / "core.v"
CORE_V_JSON = VERILOG_ROOT / "core.v.json"

REGRESSION_ARCH_TESTS_PREFIX = "test.arch_regression."

END_TEST_ADDRESS = 0xF0000000
CONSOLE_ADDRESS = 0xF0001000
ACCESS_FAULT_ADDRESS = 0x00000000

START_PC = 0x80000000
ZIFENCEI_PATTERN = re.compile(r"zifencei")


class EndTestMMIO(MemorySegment):
    def __init__(self, on_finish):
        super().__init__(range(END_TEST_ADDRESS, END_TEST_ADDRESS + 8), SegmentFlags.WRITE)
        self.on_finish = on_finish
        self.written_value = 0

    def read(self, req: ReadRequest) -> ReadReply:
        return ReadReply()

    def write(self, req: WriteRequest) -> WriteReply:
        value = 0
        for index in range(req.byte_count):
            if (req.byte_sel >> index) & 1:
                value |= ((req.data >> (8 * index)) & 0xFF) << (8 * index)

        self.written_value = value
        self.on_finish()
        return WriteReply()


class ConsoleMMIO(MemorySegment):
    def __init__(self):
        super().__init__(range(CONSOLE_ADDRESS, CONSOLE_ADDRESS + 8), SegmentFlags.WRITE)

    def read(self, req: ReadRequest) -> ReadReply:
        return ReadReply()

    def write(self, req: WriteRequest) -> WriteReply:
        data = int(req.data)
        data_bytes = data.to_bytes(req.byte_count, "little", signed=False)
        output = bytes(data_bytes[index] for index in range(req.byte_count) if (req.byte_sel >> index) & 1)
        if not output:
            output = data_bytes

        sys.stdout.buffer.write(output)
        sys.stdout.buffer.flush()
        return WriteReply()


class AccessFaultAddressMMIO(MemorySegment):
    def __init__(self):
        super().__init__(
            range(ACCESS_FAULT_ADDRESS, ACCESS_FAULT_ADDRESS + 128),
            SegmentFlags.READ | SegmentFlags.WRITE | SegmentFlags.EXECUTABLE,
        )

    def read(self, req: ReadRequest) -> ReadReply:
        return ReadReply(status=ReplyStatus.ERROR)

    def write(self, req: WriteRequest) -> WriteReply:
        return WriteReply(status=ReplyStatus.ERROR)


def get_arg_list(test_name: str, result_path: str, traces: bool = False) -> list[str]:
    arglist = ["make", "-C", str(TEST_ROOT), "-f", "arch_test.Makefile"]
    arglist += [f"_COREBLOCKS_GEN_INFO={CORE_V_JSON}"]
    arglist += [f"VERILOG_SOURCES={CORE_V}"]
    arglist += [f"TESTNAME={test_name}"]
    if result_path:
        arglist += [f"COCOTB_RESULTS_FILE={result_path}"]

    if traces:
        arglist += ["TRACES=1"]

    return arglist


def _set_transactron_env_defaults() -> None:
    os.environ.setdefault("__TRANSACTRON_LOG_LEVEL", "WARNING")
    os.environ.setdefault("__TRANSACTRON_LOG_FILTER", ".*")


def build_memory_model(elf_path: str | Path, stop_callback, **kwargs) -> tuple[CoreMemoryModel, EndTestMMIO]:
    segments = []
    segments.extend(load_segments_from_elf(str(elf_path), **kwargs))
    segments.append(ConsoleMMIO())
    segments.append(AccessFaultAddressMMIO())
    endtest = EndTestMMIO(stop_callback)
    segments.append(endtest)
    return CoreMemoryModel(segments), endtest


async def run_arch_elf(sim_backend, elf_path: str | Path, timeout_cycles: int = 2_000_000):
    _set_transactron_env_defaults()
    elf_path = Path(elf_path).resolve()

    # Tests use self-modifying code for CSR access in lower privilege modes (see CSR_ACCESS)
    mem_model, endtest = build_memory_model(
        elf_path,
        sim_backend.stop,
        disable_write_protection=ZIFENCEI_PATTERN.search(elf_path.name) is not None,
        force_executable=True,
    )

    result = await sim_backend.run(mem_model, timeout_cycles=timeout_cycles)

    assert result.success
    assert endtest.written_value == 1


async def run_test(sim_backend, test_name: str):
    elf_path = Path(arch_tests_dir) / f"{test_name}.elf"
    elf_path = elf_path.resolve()
    if not elf_path.exists():
        raise FileNotFoundError(f"ELF file not found for test {test_name}: {elf_path}")
    await run_arch_elf(sim_backend, elf_path, timeout_cycles=2_000_000)


def ensure_arch_test_cocotb_build():
    _set_transactron_env_defaults()

    VERILOG_ROOT.mkdir(parents=True, exist_ok=True)

    if VERILOG_STAMP.exists():
        return

    with FileLock(VERILOG_LOCK_FILE):
        if VERILOG_STAMP.exists():
            return

        command = [
            sys.executable,
            "-m",
            "coreblocks.gen_verilog",
            "--config",
            "full",
            "--reset-pc",
            "0x80000000",
            "--with-socks",
            "-o",
            str(CORE_V),
        ]
        subprocess.run(command, check=True, cwd=REPO_ROOT)
        VERILOG_STAMP.write_text("built\n")


def build_cocotb_module_under_lock(traces: bool) -> None:
    # Ensure the Verilog sources are present
    ensure_arch_test_cocotb_build()

    with FileLock(BUILT_LOCK_FILE):
        tmp_result_file = tempfile.NamedTemporaryFile("r")
        arglist = get_arg_list("SKIP", tmp_result_file.name, traces=traces)
        res = subprocess.run(arglist)
        if res.returncode != 0:
            raise RuntimeError("Arch test cocotb make build failed")

        tree = eT.parse(tmp_result_file.name)
        if len(list(tree.iter("failure"))) != 0:
            raise RuntimeError("Arch test cocotb make build failed with test failure")


def regression_body_with_cocotb(elf_paths: list[Path], traces: bool):
    build_cocotb_module_under_lock(traces=traces)

    my_env = dict(os.environ)
    my_env["PATH"] = str(TEST_ROOT) + ":" + my_env.get("PATH", "")

    for elf_path in elf_paths:
        tmp_result_file = tempfile.NamedTemporaryFile("r")
        arglist = get_arg_list(str(elf_path.resolve()), tmp_result_file.name, traces=traces)
        res = subprocess.run(arglist, env=my_env)
        assert res.returncode == 0

        tree = eT.parse(tmp_result_file.name)
        assert len(list(tree.iter("failure"))) == 0


def regression_body_with_pysim(elf_paths: list[Path], traces: bool):
    _set_transactron_env_defaults()
    for elf_path in elf_paths:
        traces_file = None
        if traces:
            traces_file = REGRESSION_ARCH_TESTS_PREFIX + elf_path.stem

        pysim = PySimulation(reset_pc=START_PC, with_socks=True, traces_file=traces_file)
        asyncio.run(run_arch_elf(pysim, elf_path, timeout_cycles=2_000_000))


@pytest.fixture(scope="session")
def sim_backend(request: pytest.FixtureRequest):
    return request.config.getoption("coreblocks_backend")


@pytest.fixture(scope="session")
def traces_enabled(request: pytest.FixtureRequest):
    return request.config.getoption("coreblocks_traces")


@pytest.fixture(scope="session")
def verilate_arch_model(worker_id, sim_backend, traces_enabled, request: pytest.FixtureRequest):
    """
    Fixture to prevent races when building the cocotb/Verilator model for
    arch-regression. It runs only in distributed, cocotb mode and executes a
    'SKIP' run via the arch Makefile to ensure the cocotb module is built.
    """
    if sim_backend != "cocotb" or worker_id == "master":
        yield None
        return

    build_cocotb_module_under_lock(traces=traces_enabled)
    yield


def test_entrypoint(
    arch_test_name: str, sim_backend: Literal["pysim", "cocotb"], traces_enabled: bool, verilate_arch_model
):
    path = Path(arch_tests_dir.joinpath(arch_test_name + ".elf"))
    if not path.exists():
        raise FileNotFoundError(f"ELF file not found for test {arch_test_name}: {path}")

    if sim_backend == "pysim":
        regression_body_with_pysim([path], traces=traces_enabled)
    elif sim_backend == "cocotb":
        regression_body_with_cocotb([path], traces=traces_enabled)


def main():
    parser = argparse.ArgumentParser(description="Run a single Coreblocks arch-test ELF")
    parser.add_argument("elf_path", type=Path, nargs="*", help="Paths to the ELF file to execute")
    parser.add_argument("--backend", choices=["cocotb", "pysim"], default="cocotb", help="Simulation backend")
    parser.add_argument("--timeout-cycles", type=int, default=2_000_000, help="Maximum simulated cycles")
    parser.add_argument("--traces", action="store_true", help="Enable cocotb trace generation")
    args = parser.parse_args()

    elf_paths = [path.resolve() for path in args.elf_path]

    if args.backend == "cocotb":
        regression_body_with_cocotb(elf_paths, traces=args.traces)
    elif args.backend == "pysim":
        regression_body_with_pysim(elf_paths, traces=args.traces)


if __name__ == "__main__":
    main()
