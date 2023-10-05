#!/usr/bin/env python3

import unittest
import asyncio
import argparse
import json
import re
import sys
import os
import subprocess
from typing import Literal
from pathlib import Path

topdir = Path(__file__).parent.parent
sys.path.insert(0, str(topdir))

import test.regression.benchmark  # noqa: E402
from test.regression.pysim import PySimulation  # noqa: E402
from coreblocks.params.configurations import *  # noqa: E402

str_to_coreconfig: dict[str, CoreConfiguration] = {
    "basic": basic_core_config,
    "tiny": tiny_core_config,
    "full": full_core_config,
    "vector": vector_core_config,
}


def cd_to_topdir():
    os.chdir(str(topdir))


def load_benchmarks():
    all_tests = test.regression.benchmark.get_all_benchmark_names()
    if len(all_tests) == 0:
        res = subprocess.run(["make", "-C", "test/external/embench"])
        if res.returncode != 0:
            print("Couldn't build benchmarks")
            sys.exit(1)

        all_tests = test.regression.benchmark.get_all_benchmark_names()

    exclude = {
        "cubic",
        "huffbench",
        "nbody",
        "picojpeg",
        "primecount",
        "qrduino",
        "sglib-combined",
        "st",
        "wikisort",
        "matmult-int",
        "edn",
        "nettle-aes",
        "md5sum",
        "tarfind",
    }

    return list(set(all_tests) - exclude)


def run_benchmarks_with_cocotb(benchmarks: list[str], traces: bool) -> bool:
    cpu_count = len(os.sched_getaffinity(0))
    arglist = [
        "make",
        "-C",
        "test/regression/cocotb",
        "-f",
        "benchmark.Makefile",
        "--no-print-directory",
        f"-j{cpu_count}",
    ]

    test_cases = ",".join(benchmarks)
    arglist += [f"TESTCASE={test_cases}"]

    if traces:
        arglist += ["TRACES=1"]

    res = subprocess.run(arglist)

    return res.returncode == 0


def run_benchmarks_with_pysim(benchmarks: list[str], traces: bool, verbose: bool, core_conf: CoreConfiguration) -> bool:
    suite = unittest.TestSuite()

    def _gen_test(test_name: str):
        def test_fn():
            traces_file = None
            if traces:
                traces_file = "benchmark." + test_name
            asyncio.run(
                test.regression.benchmark.run_benchmark(
                    PySimulation(verbose, traces_file=traces_file, core_conf=core_conf), test_name
                )
            )

        test_fn.__name__ = test_name
        test_fn.__qualname__ = test_name

        return test_fn

    for test_name in benchmarks:
        suite.addTest(unittest.FunctionTestCase(_gen_test(test_name)))

    runner = unittest.TextTestRunner(verbosity=(2 if verbose else 1))
    result = runner.run(suite)

    return result.wasSuccessful()


def run_benchmarks(
    benchmarks: list[str],
    backend: Literal["pysim", "cocotb"],
    traces: bool,
    verbose: bool,
    core_conf: CoreConfiguration,
) -> bool:
    if backend == "cocotb":
        return run_benchmarks_with_cocotb(benchmarks, traces)
    elif backend == "pysim":
        return run_benchmarks_with_pysim(benchmarks, traces, verbose, core_conf)
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-l", "--list", action="store_true", help="List all benchmarks")
    parser.add_argument("-t", "--trace", action="store_true", help="Dump waveforms")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("-b", "--backend", default="cocotb", choices=["cocotb", "pysim"], help="Simulation backend")
    parser.add_argument(
        "-c",
        "--config",
        action="store",
        default="full",
        help="Select core configuration. "
        + f"Available configurations: {', '.join(list(str_to_coreconfig.keys()))}. Default: %(default)s",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="benchmark.json",
        help="Selects output file to write information to. Default: %(default)s",
    )
    parser.add_argument("benchmark_name", nargs="?")

    args = parser.parse_args()

    benchmarks = load_benchmarks()

    if args.list:
        for name in benchmarks:
            print(name)
        return

    if args.benchmark_name:
        pattern = re.compile(args.benchmark_name)
        benchmarks = [name for name in benchmarks if pattern.search(name)]

        if not benchmarks:
            print(f"Could not find benchmark '{args.benchmark_name}'")
            sys.exit(1)

    success = run_benchmarks(benchmarks, args.backend, args.trace, args.verbose, str_to_coreconfig[args.config])
    if not success:
        print("Benchmark execution failed")
        sys.exit(1)

    results = []
    ipcs = []
    for name in benchmarks:
        with open(f"{str(test.regression.benchmark.results_dir)}/{name}.json", "r") as f:
            res = json.load(f)

        ipc = res["instr"] / res["cycle"]
        ipcs.append(ipc)

        results.append({"name": name, "unit": "Instructions Per Cycle", "value": ipc})
        print(f"Benchmark '{name}': cycles={res['cycle']}, instructions={res['instr']} ipc={ipc:.4f}")

    print(f"Average ipc={sum(ipcs)/len(ipcs):.4f}")

    with open(args.output, "w") as benchmark_file:
        json.dump(results, benchmark_file, indent=4)


if __name__ == "__main__":
    cd_to_topdir()
    main()
