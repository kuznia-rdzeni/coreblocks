from typing import Literal
from pathlib import Path
import pytest
import argparse
import re
import os
import asyncio

from .conftest import arch_tests_dir, profile_dir, evlog_dir
from test.sim.pysim import PySimulation
from test.sim.memory import (
    CoreMemoryModel,
    MMIOSegment,
    ReadReply,
    ReadRequest,
    ReplyStatus,
    SegmentFlags,
    WriteReply,
    WriteRequest,
    load_segments_from_elf,
)
from test.sim.cocotb import run_cocotb_entrypoint

REGRESSION_ARCH_TESTS_PREFIX = "test.arch_regression."

END_TEST_ADDRESS = 0xF0000000
CONSOLE_ADDRESS = 0xF0001000
INTERRUPT_GENERATOR_ADDRESS = 0xF0002000
ACCESS_FAULT_ADDRESS = 0x00000000


class EndTestMMIO(MMIOSegment):
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


class ConsoleMMIO(MMIOSegment):
    def __init__(self):
        super().__init__(range(CONSOLE_ADDRESS, CONSOLE_ADDRESS + 8), SegmentFlags.WRITE)
        self.buffer = bytearray()

    def read(self, req: ReadRequest) -> ReadReply:
        return ReadReply()

    def write(self, req: WriteRequest) -> WriteReply:
        data = int(req.data)
        data_bytes = data.to_bytes(req.byte_count, "little", signed=False)
        output = bytes(data_bytes[index] for index in range(req.byte_count) if (req.byte_sel >> index) & 1)
        if not output:
            output = data_bytes

        self.buffer.extend(output)

        while b"\n" in self.buffer:
            line, _, self.buffer = self.buffer.partition(b"\n")
            print(line.decode(errors="replace"))

        return WriteReply()

    def __del__(self):
        print(self.buffer.decode(errors="replace"), end="")


class AccessFaultAddressMMIO(MMIOSegment):
    def __init__(self):
        super().__init__(
            range(ACCESS_FAULT_ADDRESS, ACCESS_FAULT_ADDRESS + 128),
            SegmentFlags.READ | SegmentFlags.WRITE | SegmentFlags.EXECUTABLE,
        )

    def read(self, req: ReadRequest) -> ReadReply:
        return ReadReply(status=ReplyStatus.ERROR)

    def write(self, req: WriteRequest) -> WriteReply:
        return WriteReply(status=ReplyStatus.ERROR)


class InterruptGeneratorMMIO(MMIOSegment):
    def __init__(self):
        super().__init__(
            range(INTERRUPT_GENERATOR_ADDRESS, INTERRUPT_GENERATOR_ADDRESS + 4),
            SegmentFlags.WRITE,
        )
        self.value = 0

    def read(self, req: ReadRequest) -> ReadReply:
        return ReadReply()

    def write(self, req: WriteRequest) -> WriteReply:
        op_mask = req.data & ~(1 << 31)

        if req.data & (1 << 31):
            self.value |= op_mask
        else:
            self.value &= ~op_mask

        return WriteReply()


def build_memory_model(elf_path: str | Path, stop_callback, **kwargs):
    segments = []
    segments.extend(load_segments_from_elf(str(elf_path), **kwargs))
    segments.append(ConsoleMMIO())
    segments.append(AccessFaultAddressMMIO())
    int_generator = InterruptGeneratorMMIO()
    segments.append(int_generator)
    endtest = EndTestMMIO(stop_callback)
    segments.append(endtest)
    return CoreMemoryModel(segments), endtest, int_generator


async def run_arch_elf(sim_backend, elf_path: str | Path, timeout_cycles: int = 2_000_000):
    elf_path = Path(elf_path).resolve()

    # Tests use self-modifying code for CSR access in lower privilege modes (see CSR_ACCESS)
    mem_model, endtest, int_generator = build_memory_model(
        elf_path,
        sim_backend.stop,
        do_workarounds=False,
        disable_write_protection=re.match("Zifencei", elf_path.name) is not None,
        force_executable=True,
    )

    result = await sim_backend.run(
        mem_model, timeout_cycles=timeout_cycles, get_interrupt_value=lambda: int_generator.value
    )

    test_name = elf_path.name
    if result.profile is not None:
        os.makedirs(profile_dir, exist_ok=True)
        result.profile.encode(f"{profile_dir}/test.arch_regression.{test_name}.json")

    if result.evlog is not None:
        os.makedirs(evlog_dir, exist_ok=True)
        result.evlog.save(f"{evlog_dir}/test.arch_regression.{test_name}.jsonl")

    if not result.success:
        raise RuntimeError("Simulation timed out")

    if endtest.written_value != 1:
        raise RuntimeError(f"Failing test: {endtest.written_value}")


async def run_test(sim_backend, test_name: str):
    elf_path = Path(arch_tests_dir) / f"{test_name}.elf"
    elf_path = elf_path.resolve()
    if not elf_path.exists():
        raise FileNotFoundError(f"ELF file not found for test {test_name}: {elf_path}")
    await run_arch_elf(sim_backend, elf_path, timeout_cycles=2_000_000)


def regression_body_with_cocotb(elf_paths: list[Path], traces: bool):
    for elf_path in elf_paths:
        assert run_cocotb_entrypoint(
            "arch_elf_entrypoint", traces=traces, additional_args=[f"TESTNAME={elf_path}"]
        ), f"Test failed for {elf_path}"


def regression_body_with_pysim(elf_paths: list[Path], traces: bool):
    for elf_path in elf_paths:
        traces_file = None
        if traces:
            traces_file = REGRESSION_ARCH_TESTS_PREFIX + elf_path.stem

        pysim = PySimulation(traces_file=traces_file)
        asyncio.run(run_arch_elf(pysim, elf_path, timeout_cycles=2_000_000))


@pytest.fixture(scope="session")
def sim_backend(request: pytest.FixtureRequest):
    return request.config.getoption("coreblocks_backend")


@pytest.fixture(scope="session")
def traces_enabled(request: pytest.FixtureRequest):
    return request.config.getoption("coreblocks_traces")


def test_entrypoint(arch_test_name: str, sim_backend: Literal["pysim", "cocotb"], traces_enabled: bool):
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

    os.environ.setdefault("__TRANSACTRON_LOG_LEVEL", "WARNING")
    os.environ.setdefault("__TRANSACTRON_LOG_FILTER", ".*")

    if args.backend == "cocotb":
        regression_body_with_cocotb(elf_paths, traces=args.traces)
    elif args.backend == "pysim":
        regression_body_with_pysim(elf_paths, traces=args.traces)


if __name__ == "__main__":
    main()
