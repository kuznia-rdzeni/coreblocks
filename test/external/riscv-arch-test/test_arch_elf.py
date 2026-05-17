import sys
from pathlib import Path
import argparse
import asyncio
import os
import subprocess
import tempfile
from filelock import FileLock

try:
    from cocotb import runner as cocotb_runner
except ImportError:
    cocotb_runner = None

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from test.regression.arch_elf import run_arch_elf  # noqa: E402
from test.regression.pysim import PySimulation  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[3]

BUILD_ROOT = Path(__file__).parent.resolve() / "build"
ARCH_TEST_ELF_DIR = Path(__file__).parent.resolve() / "riscv-arch-test" / "work" / "coreblocks-full" / "elfs"

VERILOG_LOCK_FILE = BUILD_ROOT / "verilog.lock"
VERILOG_STAMP = BUILD_ROOT / "verilog.built"
VERILOG_ROOT = BUILD_ROOT / "verilog"

CORE_V = VERILOG_ROOT / "core.v"
CORE_V_JSON = VERILOG_ROOT / "core.v.json"

COCOTB_ENTRYPOINT = "arch_entrypoint"
COCOTB_ELF_ENTRYPOINT = "arch_elf_entrypoint"
COCOTB_TEST_DIR = REPO_ROOT / "test" / "regression" / "cocotb"

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
        return []
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

    # try to build the verilog files
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

    # try to build the cocotb testbench for this config
    if config.built_stamp().exists():
        return

    with FileLock(config.lock_file()):
        if config.built_stamp().exists():
            return

        config.build_dir().mkdir(parents=True, exist_ok=True)
        _ = cocotb_get_runner(config)
        config.built_stamp().write_text("built\n")


def run_arch_test_elf_with_cocotb(elf_paths: list[Path], *, traces: bool = False):
    config = ArchTestConfig(traces=traces)
    _set_transactron_env_defaults()
    ensure_arch_test_cocotb_build(config)
    runner = cocotb_get_runner(config)

    for elf_path in elf_paths:
        extra_env = dict()
        extra_env["TESTNAME"] = str(elf_path)
        extra_env["_COREBLOCKS_GEN_INFO"] = str(CORE_V_JSON)

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


def run_arch_test_elf_with_pysim(elf_paths: list[Path], timeout_cycles: int = 2_000_000):
    _set_transactron_env_defaults()
    for elf_path in elf_paths:
        asyncio.run(run_arch_elf(PySimulation(), elf_path.resolve(), timeout_cycles=timeout_cycles))


def main():
    parser = argparse.ArgumentParser(description="Run a single Coreblocks arch-test ELF")
    parser.add_argument("elf_path", type=Path, nargs="*", help="Paths to the ELF file to execute")
    parser.add_argument("--backend", choices=["pysim", "cocotb"], default="pysim", help="Simulation backend")
    parser.add_argument("--timeout-cycles", type=int, default=2_000_000, help="Maximum simulated cycles")
    parser.add_argument("--traces", action="store_true", help="Enable cocotb trace generation")
    args = parser.parse_args()

    elf_paths = [path.resolve() for path in args.elf_path]

    if args.backend == "pysim":
        run_arch_test_elf_with_pysim(elf_paths, args.timeout_cycles)

    run_arch_test_elf_with_cocotb(elf_paths, traces=args.traces)


if __name__ == "__main__":
    main()
