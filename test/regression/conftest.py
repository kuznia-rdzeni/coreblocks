from glob import glob
from pathlib import Path
import pytest
import subprocess
import re

test_dir = Path(__file__).parent.parent
riscv_tests_dir = test_dir.joinpath("external/riscv-tests")
arch_tests_dir = test_dir.joinpath("external/riscv-arch-test/elfs")
profile_dir = test_dir.joinpath("__profiles__")
evlog_dir = test_dir.joinpath("__evlogs__")

ARCH_EXPECTED_FAIL = {
    # [?] misaligned exceptions should be either before address translation at the very end
    "ExceptionsS",
    "sv32_exceptions_mprv_(S|U)_Mmode",
    # [?] trap loop
    "sv32_exceptions_(S|U)mode",
    # [?] sail requires size of reservation set <= 12
    ".*exceptions.*zalrsc.*",
    "pmpzalrsc_cfg_wr",
    # misaligned amo should cause write flavoured exception
    ".*exceptions.*zaamo.*",
    "pmpzaamo_cfg_wr",
    # [?] ?????
    "InterruptsU",
    # coreblocks assertion
    r"Zifencei-.*",
}

ARCH_EXPECTED_TIMEOUT = {
    "InterruptsS",
    "InterruptsSSm",
    "sv32_pmp_on_pte_(S|U)mode",
    "U",
}


def is_arch_expected_failing(test_name: str, failset: set[str] | None = None) -> bool:
    if failset is None:
        failset = ARCH_EXPECTED_FAIL | ARCH_EXPECTED_TIMEOUT

    test_name = test_name.split("/")[-1].split(".")[0]
    return any(re.fullmatch(rf"{pattern}(-\d\d)?", test_name, re.IGNORECASE) for pattern in failset)


def get_all_test_names():
    return sorted([name[5:] for name in glob("test-*", root_dir=riscv_tests_dir)])


def get_all_arch_test_names() -> list[str]:
    if not arch_tests_dir.exists():
        return []

    return sorted(path.relative_to(arch_tests_dir).with_suffix("").as_posix() for path in arch_tests_dir.rglob("*.elf"))


def load_regression_tests() -> list[str]:
    all_tests = set(get_all_test_names())
    if len(all_tests) == 0:
        res = subprocess.run(["make", "-C", "test/external/riscv-tests"])
        if res.returncode != 0:
            print("Couldn't build regression tests")
        all_tests = set(get_all_test_names())

    exclude = {"rv32ui-ma_data", "rv32ua-lrsc", "rv32mi-breakpoint", "rv32si-dirty", "rv32mi-instret_overflow"}
    # rv32ui-ma_data - misaligned data access in unsupported (this is implementation defined - compatible with spec)
    # rv32ua-lrsc - does 1024 loads in test - too much cycles for current infrastructure
    # rv32mi-breakpoint requires debug spec
    # rv32si-dirty requires MMU
    # rv32mi-instret_overflow until #937 is solved

    return sorted(list(all_tests - exclude))


def load_arch_regression_tests() -> list[str]:
    all_tests = set(get_all_arch_test_names())
    if len(all_tests) == 0:
        res = subprocess.run(["make", "-C", "test/external/riscv-arch-test"])
        if res.returncode != 0:
            print("Couldn't build arch regression tests")
        all_tests = set(get_all_arch_test_names())

    return sorted(filter(lambda name: not is_arch_expected_failing(name), all_tests))


def is_regression_enabled(config: pytest.Config) -> bool:
    return bool(config.getoption("coreblocks_regression", default=False))  # type: ignore


def is_arch_regression_enabled(config: pytest.Config) -> bool:
    return bool(config.getoption("coreblocks_arch_regression", default=False))  # type: ignore


def pytest_generate_tests(metafunc: pytest.Metafunc):
    tests = [
        ("test_name", load_regression_tests),
        ("arch_test_name", load_arch_regression_tests),
    ]

    for test_name, loader in tests:
        if test_name in metafunc.fixturenames:
            # The list has to be always in the same order (e.g. sorted) to allow for parallel testing
            all_tests = loader()
            metafunc.parametrize(
                test_name,
                [test_name for test_name in all_tests],
            )


def pytest_ignore_collect(collection_path, config: pytest.Config):
    collection_name = Path(str(collection_path)).name

    # Skip arch-regression module only when arch-tests are not enabled
    if collection_name == "test_arch_regression.py" and not is_arch_regression_enabled(config):
        return True

    # Skip riscv regression module only when riscv-tests are not enabled
    if collection_name == "test_regression.py" and not is_regression_enabled(config):
        return True

    return False


def pytest_runtest_setup(item: pytest.Item):
    if not is_regression_enabled(item.config) and not is_arch_regression_enabled(item.config):
        pytest.skip("need --coreblocks-regression or --coreblocks-arch-regression option to run this test")
