import shutil
from pathlib import Path
import json

from filelock import FileLock

from .core import REGRESSION_CORE

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_ROOT = Path(__file__).resolve().parent / "build"

VERILOG_ROOT = BUILD_ROOT / "verilog"
CORE_V = VERILOG_ROOT / "core.v"
CORE_V_JSON = VERILOG_ROOT / "core.v.json"
CORE_V_VLT = VERILOG_ROOT / "core.v.vlt"

VERILOG_LOCK = BUILD_ROOT / "verilog.lock"
VERILOG_STAMP = BUILD_ROOT / "verilog.stamp"


def _get_public_signals(core_json):
    with open(core_json) as file:
        j = json.load(file)
    sigs = []

    for metric in j["metrics_location"].values():
        sigs += metric["regs"].values()

    for log in j["logs"]:
        sigs.append(log["trigger_location"])
        sigs += log["fields_location"]

    evlog = j["evlog"]
    sigs.append(evlog["triggers_location"])
    for loc in evlog["site_locations"]:
        sigs.append(loc["trigger"])
        sigs += loc["fields"]

    return sigs


def _make_verilator_control(path, core_json) -> None:
    signals = _get_public_signals(core_json)
    with open(path, "w") as file:
        file.write("`verilator_config\n")
        for sig in signals:
            sig_name = sig[-1]
            sig_module = ".".join(sig[:-1])
            if len(sig) > 2:
                sig_module = f"\\{sig_module}"
            file.write(f'public_flat_rd -module "{sig_module}" -var "{sig_name}"\n')


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
        _make_verilator_control(CORE_V_VLT, CORE_V_JSON)
        VERILOG_STAMP.touch()
