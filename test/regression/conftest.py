from glob import glob
from pathlib import Path
import pytest
import subprocess
import sys

test_dir = Path(__file__).parent.parent
riscv_tests_dir = test_dir.joinpath("external/riscv-tests")


def get_all_test_names():
    return sorted([name[5:] for name in glob("test-*", root_dir=riscv_tests_dir)])


def load_regression_tests() -> list[str]:
    all_tests = set(get_all_test_names())
    if len(all_tests) == 0:
        res = subprocess.run(["make", "-C", "test/external/riscv-tests"])
        if res.returncode != 0:
            print("Couldn't build regression tests")
            sys.exit(1)
        all_tests = set(get_all_test_names())

    exclude = {"rv32ui-ma_data", "rv32ui-fence_i"}

    return sorted(list(all_tests - exclude))


def pytest_generate_tests(metafunc: pytest.Metafunc):
    if not metafunc.config.getoption("coreblocks_regression"):
        # Add regression to skiped tests
        metafunc.parametrize(["test_name", "backend", "traces", "verbose"], [])
        return

    all_tests = (
        load_regression_tests()
    )  # The list has to be always in the same order (e.g. sorted) to allow for parallel testing
    traces = metafunc.config.getoption("coreblocks_traces")
    backend = metafunc.config.getoption("coreblocks_backend")
    verbose = bool(metafunc.config.getoption("verbose"))
    if {"test_name", "backend", "traces", "verbose"}.issubset(metafunc.fixturenames):
        metafunc.parametrize(
            ["test_name", "backend", "traces", "verbose"],
            [(test_name, backend, traces, verbose) for test_name in all_tests],
        )
