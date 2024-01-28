import pytest

def pytest_addoption(parser : pytest.Parser):
    group = parser.getgroup("coreblocks")
    group.addoption("--coreblocks-regression", action="store_true", help = "Run also regression tests.")
    group.addoption(
        "--coreblocks-backend", default="cocotb", choices=["cocotb", "pysim"], help="Simulation backend for regression tests"
    )
    group.addoption( "--coreblocks-traces", action="store_true", help = "Generate traces from regression tests")
