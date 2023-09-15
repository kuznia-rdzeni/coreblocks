#!/usr/bin/env python3

import asyncio
import argparse
import sys
import os
from typing import Literal

if __name__ == "__main__":
    parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, parent)

import test.regression.signature  # noqa: E402
from test.regression.pysim import PySimulation  # noqa: E402


# def run_with_cocotb(benchmarks: list[str], traces: bool) -> bool:
#    arglist = ["make", "-C", "test/regression/cocotb", "-f", "benchmark.Makefile", "--no-print-directory"]
#
#    test_cases = ",".join(benchmarks)
#    arglist += [f"TESTCASE={test_cases}"]
#
#    if traces:
# 3        arglist += ["TRACES=1"]
#
#    res = subprocess.run(arglist)
#
#    return res.returncode == 0


def run_with_pysim(test_name: str, traces: bool, verbose: bool, output: str) -> bool:
    traces_file = None
    if traces:
        traces_file = os.path.basename(test_name)
    try:
        asyncio.run(
            test.regression.signature.run_test(PySimulation(verbose, traces_file=traces_file), test_name, output)
        )
    except RuntimeError as e:
        print("RuntimeError:", e)
        return False
    return True


def run_test(test: str, backend: Literal["pysim", "cocotb"], traces: bool, verbose: bool, output: str) -> bool:
    # if backend == "cocotb":
    #    return run_benchmarks_with_cocotb(test, traces)
    # elif backend == "pysim":
    return run_with_pysim(test, traces, verbose, output)
    # return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-t", "--trace", action="store_true", help="Dump waveforms")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("-b", "--backend", default="pysim", choices=["cocotb", "pysim"], help="Simulation backend")
    parser.add_argument("-o", "--output", default=None, help="Selects output file to write test signature to")
    parser.add_argument("path")

    args = parser.parse_args()

    output = args.output if args.output else args.path + ".signature"

    success = run_test(args.path, args.backend, args.trace, args.verbose, output)
    if not success:
        print("Program execution failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
