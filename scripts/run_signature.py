#!/usr/bin/env python3

import asyncio
import argparse
import sys
import os
import subprocess
from typing import Literal

if __name__ == "__main__":
    parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, parent)

import test.regression.signature  # noqa: E402
from test.regression.pysim import PySimulation  # noqa: E402


def run_with_cocotb(test_name: str, traces: bool, output: str) -> bool:
    arglist = [
        "make",
        "-C",
        (parent + "/" if parent else "") + "test/regression/cocotb",
        "-f",
        "signature.Makefile",
        "--no-print-directory",
    ]

    if os.path.isfile(output):
        os.remove(output)

    arglist += [f"TESTNAME={test_name}"]
    arglist += [f"OUTPUT={output}"]

    verilog_code = f"{parent}/core.v"
    gen_info_path = f"{verilog_code}.json"

    arglist += [f"VERILOG_SOURCES={verilog_code}"]
    arglist += [f"_COREBLOCKS_GEN_INFO={gen_info_path}"]

    if traces:
        arglist += ["TRACES=1"]

    subprocess.run(arglist)

    return os.path.isfile(output)  # completed successfully if signature file was created


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
    if backend == "cocotb":
        return run_with_cocotb(test, traces, output)
    elif backend == "pysim":
        return run_with_pysim(test, traces, verbose, output)
    return False


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
        print(f"{args.path}: Program execution failed")

        if output is not None:  # create empty file on failure for checker scripts
            with open(output, "w"):
                pass

        sys.exit(1)


if __name__ == "__main__":
    main()
