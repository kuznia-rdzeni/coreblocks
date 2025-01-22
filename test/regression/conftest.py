from glob import glob
from pathlib import Path
import pytest
import subprocess

test_dir = Path(__file__).parent.parent
riscv_tests_dir = test_dir.joinpath("external/riscv-tests")
profile_dir = test_dir.joinpath("__profiles__")


def get_all_test_names():
    return sorted([name[5:] for name in glob("test-*", root_dir=riscv_tests_dir)])


def load_regression_tests() -> list[str]:
    all_tests = set(get_all_test_names())
    if len(all_tests) == 0:
        res = subprocess.run(["make", "-C", "test/external/riscv-tests"])
        if res.returncode != 0:
            print("Couldn't build regression tests")
        all_tests = set(get_all_test_names())

    exclude = {"rv32ui-ma_data", "rv32ua-lrsc"}
    # rv32ui-ma_data - misaligned data access in unsupported (this is implementateon defined - compatible with spec)
    # rv32ua-lrsc - does 1024 loads in test - too much cycles for current infrastructure

    return sorted(list(all_tests - exclude))


def pytest_generate_tests(metafunc: pytest.Metafunc):
    all_tests = (
        load_regression_tests()
    )  # The list has to be always in the same order (e.g. sorted) to allow for parallel testing
    if "test_name" in metafunc.fixturenames:
        metafunc.parametrize(
            "test_name",
            [test_name for test_name in all_tests],
        )


def pytest_runtest_setup(item: pytest.Item):
    if not item.config.getoption("--coreblocks-regression", default=False):  # type: ignore
        pytest.skip("need --coreblocks-regression option to run this test")
