import re
from typing import Optional
import pytest


def pytest_addoption(parser: pytest.Parser):
    group = parser.getgroup("coreblocks")
    group.addoption("--coreblocks-regression", action="store_true", help="Run also regression tests.")
    group.addoption(
        "--coreblocks-backend",
        default="cocotb",
        choices=["cocotb", "pysim"],
        help="Simulation backend for regression tests",
    )
    group.addoption("--coreblocks-traces", action="store_true", help="Generate traces from regression tests")
    group.addoption("--coreblocks-list", action="store_true", help="List all tests in flatten format.")
    group.addoption(
        "--coreblocks-test-name",
        action="store",
        type=str,
        help="Name or regexp in flatten format matching the tests to run.",
    )
    group.addoption(
        "--coreblocks-test-count",
        action="store",
        type=int,
        help="Number of tests to start. If less than number of all selected tests, then starts only subset of them.",
    )


def generate_unittestname(item: pytest.Item) -> str:
    full_name = ".".join(map(lambda s: s[:-3] if s[-3:] == ".py" else s, map(lambda x: x.name, item.listchain())))
    return full_name


def generate_test_cases_list(session: pytest.Session) -> list[str]:
    tests_list = []
    for item in session.items:
        full_name = generate_unittestname(item)
        tests_list.append(full_name)
    return tests_list


def pytest_collection_finish(session: pytest.Session):
    if session.config.getoption("coreblocks_list"):
        full_names = generate_test_cases_list(session)
        for i in full_names:
            print(i)


@pytest.hookimpl(tryfirst=True)
def pytest_runtestloop(session: pytest.Session) -> Optional[bool]:
    if session.config.getoption("coreblocks_list"):
        return True
    return None


def deselect_based_on_flatten_name(items: list[pytest.Item], config: pytest.Config) -> None:
    coreblocks_test_name = config.getoption("coreblocks_test_name")
    if not isinstance(coreblocks_test_name, str):
        return

    deselected = []
    remaining = []
    regexp = re.compile(coreblocks_test_name)
    for item in items:
        full_name = generate_unittestname(item)
        match = regexp.search(full_name)
        if match is None:
            deselected.append(item)
        else:
            remaining.append(item)
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = remaining


def deselect_based_on_count(items: list[pytest.Item], config: pytest.Config) -> None:
    coreblocks_test_count = config.getoption("coreblocks_test_count")
    if not isinstance(coreblocks_test_count, int):
        return

    deselected = items[coreblocks_test_count:]
    remaining = items[:coreblocks_test_count]
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = remaining


def pytest_collection_modifyitems(items: list[pytest.Item], config: pytest.Config) -> None:
    deselect_based_on_flatten_name(items, config)
    deselect_based_on_count(items, config)
