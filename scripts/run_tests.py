#!/usr/bin/env python3

import pytest
import unittest
import asyncio
import argparse
import re
import sys
import os
import subprocess
from typing import Literal
from pathlib import Path

topdir = Path(__file__).parent.parent
sys.path.insert(0, str(topdir))

import test.regression.conftest  # noqa: E402
import test.regression.test_regression  # noqa: E402
from test.regression.pysim import PySimulation  # noqa: E402

REGRESSION_TESTS_PREFIX = "test.regression."
pytest_plugins = "coreblocks_pytest_plugin"

def cd_to_testdir():
    os.chdir(str(topdir / "test"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-l", "--list", action="store_true", help="List all tests")
    parser.add_argument("-t", "--trace", action="store_true", help="Dump waveforms")
    parser.add_argument("-p", "--profile", action="store_true", help="Write execution profiles")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("-a", "--all", action="store_true", default=False, help="Run all tests")
    parser.add_argument(
        "-b", "--backend", default="cocotb", choices=["cocotb", "pysim"], help="Simulation backend for regression tests"
    )
    parser.add_argument("-c", "--count", type=int, help="Start `c` first tests which match regexp")
    parser.add_argument("-j", "--jobs", type=int, default = len(os.sched_getaffinity(0)), help="Start `j` jobs in parallel. Default: all")
    parser.add_argument("test_name", nargs="?")

    args = parser.parse_args()

    pytest_arguments=["--max-worker-restart=1"]

    if args.trace:
        os.environ["__COREBLOCKS_DUMP_TRACES"] = "1"
        pytest_arguments.append("--coreblocks-traces")

    if args.profile:
        os.environ["__TRANSACTRON_PROFILE"] = "1"

    if args.test_name:
        pytest_arguments += [f"--coreblocks-test-name={args.test_name}"]
    if args.count:
        pytest_arguments += ["--coreblocks-test-count", str(args.count)]
    if args.list:
        pytest_arguments.append("--coreblocks-list")
    if args.jobs and not args.list:
        # To list tests we have to run only one job. Otherwise there is no output (probably captured by worker server).
        pytest_arguments += ["-n", str(args.jobs)]
    if args.all:
        pytest_arguments.append("--coreblocks-regression")
    if args.verbose:
        pytest_arguments.append("--verbose")
    if args.backend:
        pytest_arguments += [f"--coreblocks-backend={args.backend}"]

    print(pytest_arguments)
    ret = pytest.main(pytest_arguments, ["coreblocks_pytest_plugin"])
    
    exit(ret)

if __name__ == "__main__":
    #cd_to_testdir()
    #pytest.main(["--coreblocks-list"], ["coreblocks_pytest_plugin"])
    main()
