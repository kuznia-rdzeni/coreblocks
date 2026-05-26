from typing import Literal
from pathlib import Path
from filelock import FileLock

import pytest
import argparse
import asyncio
import os
import re
import subprocess
import sys
import tempfile

try:
    from cocotb import runner as cocotb_runner
except ImportError:
    cocotb_runner = None

from .conftest import arch_tests_dir
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
BUILD_ROOT = Path(__file__).resolve().parent / "cocotb" / "build"
ARCH_TEST_DIR = REPO_ROOT / "test" / "external" / "riscv-arch-test"
ARCH_TEST_ELF_DIR = ARCH_TEST_DIR / "elfs"

VERILOG_LOCK_FILE = BUILD_ROOT / "verilog.lock"
VERILOG_STAMP = BUILD_ROOT / "verilog.built"
VERILOG_ROOT = BUILD_ROOT / "verilog"

CORE_V = VERILOG_ROOT / "core.v"
CORE_V_JSON = VERILOG_ROOT / "core.v.json"

COCOTB_ELF_ENTRYPOINT = "arch_elf_entrypoint"
COCOTB_TEST_DIR = REPO_ROOT / "test" / "regression" / "cocotb"
ARCH_REGRESSION_TESTS_PREFIX = "test.regression.arch."

BUILD_ARGS = [
    "-Wno-CASEINCOMPLETE",
    "-Wno-CASEOVERLAP",
    "-Wno-WIDTHEXPAND",
    "-Wno-WIDTHTRUNC",
    "-Wno-UNSIGNED",
    "-Wno-CMPCONST",
    "-Wno-LITENDIAN",
    "-Wno-ALWNEVER",
    "-Wno-UNOPTFLAT",
]

ZIFENCEI_PATTERN = re.compile("zifencei", re.IGNORECASE)

END_TEST_ADDRESS = 0xF0000000
CONSOLE_ADDRESS = 0xF0001000
ACCESS_FAULT_ADDRESS = 0x00000010


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
            range(ACCESS_FAULT_ADDRESS, ACCESS_FAULT_ADDRESS + 8),
            SegmentFlags.READ | SegmentFlags.WRITE | SegmentFlags.EXECUTABLE,
        )

    def read(self, req: ReadRequest) -> ReadReply:
        return ReadReply(status=ReplyStatus.ERROR)

    def write(self, req: WriteRequest) -> WriteReply:
        return WriteReply(status=ReplyStatus.ERROR)


class ArchTestConfig:
    simulator: str
    traces: bool

    def __init__(self, traces: bool, simulator: str | None = None):
        self.traces = traces
        self.simulator = simulator or os.getenv("SIM", "verilator")

    def config_name(self) -> str:
        name = self.simulator
        if self.traces:
            name += "_traces"
        return name

    def build_dir(self) -> Path:
        return BUILD_ROOT / self.config_name()

    def lock_file(self) -> Path:
        return BUILD_ROOT / f"{self.config_name()}.lock"

    def built_stamp(self) -> Path:
        return BUILD_ROOT / f"{self.config_name()}.built"

    def extra_args(self) -> list[str]:
        args = []
        if self.traces:
            args.append("--trace-fst")
            args.append("--trace-structs")
        return args


def _set_transactron_env_defaults() -> None:
    os.environ.setdefault("__TRANSACTRON_LOG_LEVEL", "WARNING")
    os.environ.setdefault("__TRANSACTRON_LOG_FILTER", ".*")

    makeflags = os.environ.get("MAKEFLAGS", "")
    if "-j" not in makeflags and "--jobs" not in makeflags:
        num_cpus = os.cpu_count() or 1
        os.environ["MAKEFLAGS"] = makeflags + f" -j{num_cpus}"


def discover_arch_test_elves() -> list[Path]:
    if not ARCH_TEST_ELF_DIR.exists():
        res = subprocess.run(["make", "-C", str(ARCH_TEST_DIR)], check=True)
        if res.returncode != 0:
            raise RuntimeError("Couldn't build arch regression tests")
    return sorted(path.resolve() for path in ARCH_TEST_ELF_DIR.rglob("*.elf"))


def cocotb_get_runner(config: ArchTestConfig):
    if cocotb_runner is None:
        raise RuntimeError("cocotb not found")

    runner = cocotb_runner.get_runner(config.simulator)
    runner.build(
        sources=[str(CORE_V)],
        build_dir=config.build_dir(),
        build_args=BUILD_ARGS + config.extra_args(),
        hdl_toplevel="top",
    )
    return runner


def ensure_arch_test_cocotb_build(config: ArchTestConfig) -> None:
    _set_transactron_env_defaults()

    BUILD_ROOT.mkdir(parents=True, exist_ok=True)

    if not VERILOG_STAMP.exists():
        with FileLock(VERILOG_LOCK_FILE):
            if not VERILOG_STAMP.exists():
                VERILOG_ROOT.mkdir(parents=True, exist_ok=True)
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

    if config.built_stamp().exists():
        return

    with FileLock(config.lock_file()):
        if config.built_stamp().exists():
            return

        config.build_dir().mkdir(parents=True, exist_ok=True)
        _ = cocotb_get_runner(config)
        config.built_stamp().write_text("built\n")


def build_memory_model(elf_path: str | Path, stop_callback, **kwargs) -> tuple[CoreMemoryModel, EndTestMMIO]:
    segments = []
    segments.extend(load_segments_from_elf(str(elf_path), **kwargs))
    segments.append(ConsoleMMIO())
    segments.append(AccessFaultAddressMMIO())
    endtest = EndTestMMIO(stop_callback)
    segments.append(endtest)
    return CoreMemoryModel(segments), endtest


async def run_arch_elf(sim_backend, elf_path: str | Path, timeout_cycles: int = 2_000_000):
    os.environ.setdefault("__TRANSACTRON_LOG_LEVEL", "WARNING")
    os.environ.setdefault("__TRANSACTRON_LOG_FILTER", ".*")

    elf_path = Path(elf_path).resolve()

    mem_model, endtest = build_memory_model(
        elf_path,
        sim_backend.stop,
        disable_write_protection=ZIFENCEI_PATTERN.search(elf_path.name) is not None,
    )

    result = await sim_backend.run(mem_model, timeout_cycles=timeout_cycles)

    assert result.success
    assert endtest.written_value == 1


async def run_test(sim_backend, test_name: str):
    elf_path = arch_tests_dir.joinpath(test_name + ".elf")
    await run_arch_elf(sim_backend, elf_path, timeout_cycles=2_000_000)


def run_arch_test_elf_with_cocotb(elf_paths: list[Path], *, traces: bool = False):
    config = ArchTestConfig(traces=traces)
    _set_transactron_env_defaults()
    ensure_arch_test_cocotb_build(config)
    runner = cocotb_get_runner(config)

    for elf_path in elf_paths:
        elf_path = elf_path.resolve()
        extra_env = {
            "TESTNAME": str(elf_path),
            "_COREBLOCKS_GEN_INFO": str(CORE_V_JSON),
        }

        results_file = tempfile.NamedTemporaryFile(suffix=".xml", prefix="cocotb_results_", delete=False)

        runner.test(
            test_module=COCOTB_ELF_ENTRYPOINT,
            hdl_toplevel="top",
            build_dir=config.build_dir(),
            test_dir=COCOTB_TEST_DIR,
            extra_env=extra_env,
            test_args=config.extra_args(),
            results_xml=str(results_file.name),
        )

        assert cocotb_runner is not None
        _, fails = cocotb_runner.get_results(Path(results_file.name))
        assert fails == 0


@pytest.fixture
def sim_backend(request: pytest.FixtureRequest):
    return request.config.getoption("coreblocks_backend")


@pytest.fixture
def traces_enabled(request: pytest.FixtureRequest):
    return request.config.getoption("coreblocks_traces")


def test_entrypoint(arch_test_name: str, sim_backend: Literal["pysim", "cocotb"], traces_enabled: bool):
    # TODO: add pysim support
    if sim_backend != "cocotb":
        raise NotImplementedError("Only cocotb backend is supported for arch regression tests")

    path = Path(arch_tests_dir.joinpath(arch_test_name + ".elf"))
    run_arch_test_elf_with_cocotb([path], traces=traces_enabled)


def main():
    parser = argparse.ArgumentParser(description="Run a single Coreblocks arch-test ELF")
    parser.add_argument("elf_path", type=Path, nargs="*", help="Paths to the ELF file to execute")
    parser.add_argument("--backend", choices=["cocotb"], default="cocotb", help="Simulation backend")
    parser.add_argument("--timeout-cycles", type=int, default=2_000_000, help="Maximum simulated cycles")
    parser.add_argument("--traces", action="store_true", help="Enable cocotb trace generation")
    args = parser.parse_args()

    elf_paths = [path.resolve() for path in args.elf_path]

    # TODO: add pysim support
    run_arch_test_elf_with_cocotb(elf_paths, traces=args.traces)


if __name__ == "__main__":
    main()
