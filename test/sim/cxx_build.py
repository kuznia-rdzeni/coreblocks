"""Building the C++ simulator.

One shared library serves every regression suite - riscv-tests, arch tests and
benchmarks.
"""

import argparse
import hashlib
import shutil
import subprocess
import sysconfig
from importlib.machinery import EXTENSION_SUFFIXES
from pathlib import Path

from filelock import FileLock

from .verilog import BUILD_ROOT, CORE_V, clean_core_verilog, ensure_core_verilog_generated

CXX_ROOT = Path(__file__).resolve().parent / "cxx"
BUILD_DIR = BUILD_ROOT / "cxxsim"
BUILD_LOCK = BUILD_ROOT / "cxxsim.lock"

MODULE_NAME = "coreblocks_cxxsim"
MODULE_PATH = BUILD_DIR / (MODULE_NAME + EXTENSION_SUFFIXES[0])
CORE_LIB = BUILD_DIR / "libVtop.a"
RUNTIME_LIB = BUILD_DIR / "libverilated.a"

SOURCES = ["module.cpp", "memory.cpp", "simulation.cpp", "wishbone.cpp"]

VERILATOR_WARNING_FLAGS = [
    "-Wno-CASEINCOMPLETE",
    "-Wno-CASEOVERLAP",
    "-Wno-WIDTHEXPAND",
    "-Wno-WIDTHTRUNC",
    "-Wno-UNSIGNED",
    "-Wno-CMPCONST",
    "-Wno-LITENDIAN",
    "-Wno-UNOPTFLAT",
]

MODULE_CXX_FLAGS = [
    "-std=c++17",
    "-fPIC",
    "-fvisibility=hidden",
    "-Os",
    "-fstrict-aliasing",
    "-Wall",
    "-Wextra",
    "-Wpedantic",
]

# The verilated core ends up in a shared library, so it has to be position independent.
VERILATED_CXX_FLAGS = ["-fPIC"]


def _verilator_version() -> tuple[int, ...]:
    output = subprocess.run(["verilator", "--version"], check=True, capture_output=True, text=True).stdout
    return tuple(int(part) for part in output.split()[1].split("."))


def _verilator_root() -> Path:
    output = subprocess.run(
        ["verilator", "--getenv", "VERILATOR_ROOT"], check=True, capture_output=True, text=True
    ).stdout
    return Path(output.strip())


def _verilate_command() -> list[str]:
    """Builds the verilated core into a static library."""
    command = [
        "verilator",
        "--cc",
        str(CORE_V),
        "--top-module",
        "top",
        "--prefix",
        "Vtop",
        "-Mdir",
        str(BUILD_DIR),
        "--build",
        "-j",
        "0",
        "-O3",
        "--no-timing",
        "--x-initial",
        "fast",
        "-CFLAGS",
        " ".join(VERILATED_CXX_FLAGS),
    ]
    command += VERILATOR_WARNING_FLAGS
    if _verilator_version() >= (5, 40):
        command += ["-Wno-ALWNEVER"]

    return command


def _module_command() -> list[str]:
    """Links the verilated core and the simulator into a Python extension module."""
    try:
        import pybind11
    except ImportError:
        raise RuntimeError("Building the cxxsim backend requires pybind11")

    verilator_root = _verilator_root()
    includes = {sysconfig.get_paths()["include"], sysconfig.get_paths()["platinclude"], pybind11.get_include()}

    command = ["g++", "-shared"] + MODULE_CXX_FLAGS
    command += [f"-I{include}" for include in sorted(includes)]
    command += [
        f"-I{BUILD_DIR}",
        "-isystem",
        f"{verilator_root}/include",
        "-isystem",
        f"{verilator_root}/include/vltstd",
    ]
    command += [str(CXX_ROOT / source) for source in SOURCES]
    command += [f"-L{BUILD_DIR}", "-lVtop", "-lverilated"]
    command += ["-o", str(MODULE_PATH)]

    return command


def _fingerprint(command: list[str], files: list[Path]) -> str:
    digest = hashlib.sha256()
    digest.update(" ".join(command).encode())

    for file in files:
        digest.update(file.read_bytes())

    return digest.hexdigest()


def _build_step(description: str, stamp_name: str, product: Path, command: list[str], fingerprint: str) -> bool:
    """Runs one build step, unless its result is already up to date."""
    stamp = BUILD_DIR / stamp_name

    if product.exists() and stamp.exists() and stamp.read_text() == fingerprint:
        return False

    print(f"{description}...", flush=True)

    stamp.unlink(missing_ok=True)
    subprocess.run(command, check=True, cwd=CXX_ROOT)
    stamp.write_text(fingerprint)

    return True


def ensure_cxxsim_built():
    ensure_core_verilog_generated()

    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    with FileLock(BUILD_LOCK):
        verilate_command = _verilate_command()
        _build_step(
            "Verilating the core, this takes a few minutes",
            "verilate.stamp",
            CORE_LIB,
            verilate_command,
            _fingerprint(verilate_command, [CORE_V]),
        )

        module_command = _module_command()
        sources = sorted(CXX_ROOT.glob("*.h")) + [CXX_ROOT / source for source in SOURCES]
        sources += [CORE_LIB, RUNTIME_LIB]
        _build_step(
            "Building the simulator module",
            f"module{EXTENSION_SUFFIXES[0]}.stamp",
            MODULE_PATH,
            module_command,
            _fingerprint(module_command, sources),
        )


def clean_cxxsim_build():
    BUILD_ROOT.mkdir(parents=True, exist_ok=True)

    with FileLock(BUILD_LOCK):
        shutil.rmtree(BUILD_DIR, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description="Build the C++ simulator for coreblocks")
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Discard the generated Verilog and the built simulator first",
    )
    args = parser.parse_args()

    if args.clean:
        print("Discarding the generated Verilog and the built simulator...", flush=True)
        clean_core_verilog()
        clean_cxxsim_build()

    ensure_cxxsim_built()
    print(f"Built {MODULE_PATH}")


if __name__ == "__main__":
    main()
