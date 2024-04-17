#!/usr/bin/env python3

import unittest
import asyncio
import argparse
import json
import re
import sys
import os
import subprocess
import tabulate
from typing import Literal
from pathlib import Path

topdir = Path(__file__).parent.parent
sys.path.insert(0, str(topdir))

import test.regression.benchmark  # noqa: E402
from test.regression.benchmark import BenchmarkResult  # noqa: E402
from test.regression.pysim import PySimulation  # noqa: E402


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
    arglist = ["make", "-C", "test/regression/cocotb", "-f", "benchmark.Makefile", "--no-print-directory"]

    test_cases = ",".join(benchmarks)
    arglist += [f"TESTCASE={test_cases}"]

    verilog_code = topdir.joinpath("core.v")
    gen_info_path = f"{verilog_code}.json"

    arglist += [f"VERILOG_SOURCES={verilog_code}"]
    arglist += [f"_COREBLOCKS_GEN_INFO={gen_info_path}"]

    if traces:
        arglist += ["TRACES=1"]

    res = subprocess.run(arglist)

    return res.returncode == 0


def run_benchmarks_with_pysim(benchmarks: list[str], traces: bool) -> bool:
    suite = unittest.TestSuite()

    def _gen_test(test_name: str):
        def test_fn():
            traces_file = None
            if traces:
                traces_file = "benchmark." + test_name
            asyncio.run(test.regression.benchmark.run_benchmark(PySimulation(traces_file=traces_file), test_name))

        test_fn.__name__ = test_name
        test_fn.__qualname__ = test_name

        return test_fn

    for test_name in benchmarks:
        suite.addTest(unittest.FunctionTestCase(_gen_test(test_name)))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


def run_benchmarks(benchmarks: list[str], backend: Literal["pysim", "cocotb"], traces: bool) -> bool:
    if backend == "cocotb":
        return run_benchmarks_with_cocotb(benchmarks, traces)
    elif backend == "pysim":
        return run_benchmarks_with_pysim(benchmarks, traces)
    return False


def build_result_table(results: dict[str, BenchmarkResult], tablefmt: str) -> str:
    if len(results) == 0:
        return ""

    header = ["Testbench name", "Cycles", "Instructions", "IPC"]

    # First fetch all metrics names to build the header
    result = next(iter(results.values()))
    for metric_name in sorted(result.metric_values.keys()):
        regs = result.metric_values[metric_name]
        for reg_name in regs:
            header.append(f"{metric_name}/{reg_name}")

    columns = [header]
    for benchmark_name, result in results.items():
        ipc = result.instr / result.cycles

        column = [benchmark_name, result.cycles, result.instr, ipc]

        for metric_name in sorted(result.metric_values.keys()):
            regs = result.metric_values[metric_name]
            for reg_name in regs:
                column.append(regs[reg_name])

        columns.append(column)

    # Transpose the table, as the library expects to get a list of rows (and we have a list of columns).
    rows = [list(i) for i in zip(*columns)]

    return tabulate.tabulate(rows, headers="firstrow", tablefmt=tablefmt)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-l", "--list", action="store_true", help="List all benchmarks")
    parser.add_argument("-t", "--trace", action="store_true", help="Dump waveforms")
    parser.add_argument("--log-level", default="WARNING", action="store", help="Level of messages to display.")
    parser.add_argument("--log-filter", default=".*", action="store", help="Regexp used to filter out logs.")
    parser.add_argument("-p", "--profile", action="store_true", help="Write execution profiles")
    parser.add_argument("-b", "--backend", default="cocotb", choices=["cocotb", "pysim"], help="Simulation backend")
    parser.add_argument(
        "-o",
        "--output",
        default="benchmark.json",
        help="Selects output file to write information to. Default: %(default)s",
    )
    parser.add_argument("--summary", default="", action="store", help="Write Markdown summary to this file")
    parser.add_argument("benchmark_name", nargs="?")

    args = parser.parse_args()

    benchmarks = load_benchmarks()

    if args.list:
        for name in benchmarks:
            print(name)
        return

    os.environ["__TRANSACTRON_LOG_LEVEL"] = args.log_level
    os.environ["__TRANSACTRON_LOG_FILTER"] = args.log_filter

    if args.benchmark_name:
        pattern = re.compile(args.benchmark_name)
        benchmarks = [name for name in benchmarks if pattern.search(name)]

        if not benchmarks:
            print(f"Could not find benchmark '{args.benchmark_name}'")
            sys.exit(1)

    if args.profile:
        os.environ["__TRANSACTRON_PROFILE"] = "1"

    success = run_benchmarks(benchmarks, args.backend, args.trace)
    if not success:
        print("Benchmark execution failed")
        sys.exit(1)

    ipcs = []

    results: dict[str, BenchmarkResult] = {}

    for name in benchmarks:
        with open(f"{str(test.regression.benchmark.results_dir)}/{name}.json", "r") as f:
            result = BenchmarkResult.from_json(f.read())  # type: ignore

        results[name] = result

        ipc = result.instr / result.cycles
        ipcs.append({"name": name, "unit": "Instructions Per Cycle", "value": ipc})

    print(build_result_table(results, "simple_outline"))

    if args.summary != "":
        with open(args.summary, "w") as summary_file:
            print(build_result_table(results, "github"), file=summary_file)

    with open(args.output, "w") as benchmark_file:
        json.dump(ipcs, benchmark_file, indent=4)


if __name__ == "__main__":
    cd_to_topdir()
    main()
