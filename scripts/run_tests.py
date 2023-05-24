#!/usr/bin/env python3

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

import test.regression.test  # noqa: E402
from test.regression.pysim import PySimulation  # noqa: E402

REGRESSION_TESTS_PREFIX = "test.regression."


def cd_to_topdir():
    os.chdir(str(topdir))


def load_unit_tests():
    suite = unittest.TestLoader().discover(".")

    tests = {}

    def flatten(suite):
        if hasattr(suite, "__iter__"):
            for x in suite:
                flatten(x)
        else:
            tests[suite.id()] = suite

    flatten(suite)

    return tests


def load_regression_tests() -> list[str]:
    all_tests = test.regression.test.get_all_test_names()
    if len(all_tests) == 0:
        res = subprocess.run(["make", "-C", "test/external/riscv-tests"])
        if res.returncode != 0:
            print("Couldn't build regression tests")
            sys.exit(1)

    exclude = {"rv32ui-ma_data", "rv32ui-fence_i", "rv32um-div", "rv32um-divu", "rv32um-rem", "rv32um-remu"}

    return list(all_tests - exclude)


def run_regressions_with_cocotb(tests: list[str], traces: bool) -> bool:
    arglist = ["make", "-C", "test/regression/cocotb", "-f", "test.Makefile"]

    test_cases = ",".join(tests)
    arglist += [f"TESTCASE={test_cases}"]

    if traces:
        arglist += ["TRACES=1"]

    res = subprocess.run(arglist)

    return res.returncode == 0


def run_regressions_with_pysim(tests: list[str], traces: bool, verbose: bool) -> bool:
    suite = unittest.TestSuite()

    def _gen_test(test_name: str):
        def test_fn():
            traces_file = None
            if traces:
                traces_file = REGRESSION_TESTS_PREFIX + test_name
            asyncio.run(test.regression.test.run_test(PySimulation(verbose, traces_file=traces_file), test_name))

        test_fn.__name__ = test_name
        test_fn.__qualname__ = test_name

        return test_fn

    for test_name in tests:
        suite.addTest(unittest.FunctionTestCase(_gen_test(test_name)))

    runner = unittest.TextTestRunner(verbosity=(2 if verbose else 1))
    result = runner.run(suite)

    return result.wasSuccessful()


def run_regression_tests(tests: list[str], backend: Literal["pysim", "cocotb"], traces: bool, verbose: bool) -> bool:
    if backend == "cocotb":
        return run_regressions_with_cocotb(tests, traces)
    elif backend == "pysim":
        return run_regressions_with_pysim(tests, traces, verbose)
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-l", "--list", action="store_true", help="List all tests")
    parser.add_argument("-t", "--trace", action="store_true", help="Dump waveforms")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("-a", "--all", action="store_true", default=False, help="Run all tests")
    parser.add_argument(
        "-b", "--backend", default="cocotb", choices=["cocotb", "pysim"], help="Simulation backend for regression tests"
    )
    parser.add_argument("-c", "--count", type=int, help="Start `c` first tests which match regexp")
    parser.add_argument("test_name", nargs="?")

    args = parser.parse_args()

    unit_tests = load_unit_tests()
    regression_tests = load_regression_tests() if args.all else []

    if args.list:
        for name in list(unit_tests.keys()):
            print(name)
        for name in regression_tests:
            print(REGRESSION_TESTS_PREFIX + name)
        return

    if args.trace:
        os.environ["__COREBLOCKS_DUMP_TRACES"] = "1"

    if args.test_name:
        pattern = re.compile(args.test_name)
        unit_tests = {name: test for name, test in unit_tests.items() if pattern.search(name)}
        regression_tests = [test for test in regression_tests if pattern.search(REGRESSION_TESTS_PREFIX + test)]

        if not unit_tests and not regression_tests:
            print(f"Could not find test matching '{args.test_name}'")
            sys.exit(1)

    unit_tests_success = True
    if unit_tests:
        runner = unittest.TextTestRunner(verbosity=(2 if args.verbose else 1))
        result = runner.run(unittest.TestSuite(list(unit_tests.values())[: args.count]))
        unit_tests_success = result.wasSuccessful()

    regression_tests_success = True
    if regression_tests:
        regression_tests_success = run_regression_tests(regression_tests, args.backend, args.trace, args.verbose)

    sys.exit(not (unit_tests_success and regression_tests_success))


if __name__ == "__main__":
    cd_to_topdir()
    main()
