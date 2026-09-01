import shutil
from pathlib import Path

from filelock import FileLock

from .core import REGRESSION_CORE

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_ROOT = Path(__file__).resolve().parent / "build"

VERILOG_ROOT = BUILD_ROOT / "verilog"
CORE_V = VERILOG_ROOT / "core.v"
CORE_V_JSON = VERILOG_ROOT / "core.v.json"

VERILOG_LOCK = BUILD_ROOT / "verilog.lock"
VERILOG_STAMP = BUILD_ROOT / "verilog.stamp"


def clean_core_verilog():
    BUILD_ROOT.mkdir(parents=True, exist_ok=True)

    with FileLock(VERILOG_LOCK):
        VERILOG_STAMP.unlink(missing_ok=True)
        shutil.rmtree(VERILOG_ROOT, ignore_errors=True)


def ensure_core_verilog_generated():
    VERILOG_ROOT.mkdir(parents=True, exist_ok=True)

    if VERILOG_STAMP.exists():
        return

    with FileLock(VERILOG_LOCK):
        if VERILOG_STAMP.exists():
            return

        print("Generating the core Verilog...", flush=True)

        REGRESSION_CORE.generate_verilog(CORE_V)
        VERILOG_STAMP.touch()
