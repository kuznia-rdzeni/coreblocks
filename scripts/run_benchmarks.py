#!/usr/bin/env python3

import asyncio
import argparse
import json
import re
import sys
import os
import subprocess
import tabulate
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Literal
from pathlib import Path

topdir = Path(__file__).parent.parent
sys.path.insert(0, str(topdir))

import test.benchmark.benchmark  # noqa: E402
from test.benchmark.benchmark import BenchmarkResult  # noqa: E402
from test.sim.common import SimulationBackend  # noqa: E402
from test.sim.pysim import PySimulation  # noqa: E402
from test.sim.cocotb import clean_cocotb_build, run_cocotb_entrypoint  # noqa: E402
from test.sim.verilog import clean_core_verilog  # noqa: E402


def cd_to_topdir():
    os.chdir(str(topdir))


def load_benchmarks():
    all_tests = test.benchmark.benchmark.get_all_benchmark_names()
    if len(all_tests) == 0:
        res = subprocess.run(["make", "-C", "test/external/embench"])
        if res.returncode != 0:
            print("Couldn't build benchmarks")
            sys.exit(1)

        all_tests = test.benchmark.benchmark.get_all_benchmark_names()

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

    ret = list(set(all_tests) - exclude)
    ret.sort()
    return ret


def clean_build_artifacts(backend: Literal["pysim", "cocotb"]):
    if backend == "pysim":
        return

    print("Discarding the generated Verilog and the built testbench...")

    clean_core_verilog()
    clean_cocotb_build()


def run_benchmarks_with_cocotb(benchmarks: list[str], traces: bool) -> bool:
    return run_cocotb_entrypoint(
        "benchmark_entrypoint",
        traces=traces,
        additional_args=[
            "--no-print-directory",
            f"TESTCASE={','.join(benchmarks)}",
        ],
    )


def run_benchmarks_with_backend(
    benchmarks: list[str], make_backend: Callable[[str], SimulationBackend], jobs: int
) -> bool:
    failures: list[str] = []

    def run_one(benchmark_name: str):
        asyncio.run(test.benchmark.benchmark.run_benchmark(make_backend(benchmark_name), benchmark_name))

    with ThreadPoolExecutor(max_workers=jobs) as executor:
        futures = {executor.submit(run_one, name): name for name in benchmarks}

        for done, future in enumerate(as_completed(futures), start=1):
            name = futures[future]
            progress = f"[{done}/{len(benchmarks)}]"
            try:
                future.result()
            except Exception as e:
                failures.append(name)
                print(f"{progress} FAIL {name}: {e}")
            else:
                print(f"{progress} ok   {name}")

    if failures:
        print(f"{len(failures)} of {len(benchmarks)} benchmarks failed: {', '.join(sorted(failures))}")

    return not failures


def run_benchmarks_with_pysim(benchmarks: list[str], traces: bool, jobs: int) -> bool:
    def make_backend(benchmark_name: str) -> SimulationBackend:
        return PySimulation(traces_file="benchmark." + benchmark_name if traces else None)

    return run_benchmarks_with_backend(benchmarks, make_backend, jobs)


def run_benchmarks(benchmarks: list[str], backend: Literal["pysim", "cocotb"], traces: bool, jobs: int) -> bool:
    # The cocotb backend schedules the benchmarks inside its own testbench.
    parallelism = "" if backend == "cocotb" else f", {jobs} at a time"
    print(f"Running {len(benchmarks)} benchmarks with the {backend} backend{parallelism}", flush=True)

    if backend == "cocotb":
        return run_benchmarks_with_cocotb(benchmarks, traces)
    elif backend == "pysim":
        return run_benchmarks_with_pysim(benchmarks, traces, jobs)
    return False


def build_result_table(results: dict[str, BenchmarkResult], tablefmt: str) -> str:
    if len(results) == 0:
        return ""

    header = [
        "Testbench name",
        "Cycles",
        "Instructions",
        "IPC",
        "Mispredicts/1k instr",
        "Wall time [s]",
        "Sim speed [kcycles/s]",
    ]

    # First fetch all metrics names to build the header
    result = next(iter(results.values()))
    for metric_name in sorted(result.metric_values.keys()):
        regs = result.metric_values[metric_name]
        for reg_name in regs:
            header.append(f"{metric_name}/{reg_name}")

    columns = [header]
    for benchmark_name, result in results.items():
        ipc = result.instr / result.cycles
        mpki = result.mispredicts / result.instr * 1000

        speed = result.simulated_cycles / result.wall_time / 1000 if result.wall_time else 0

        column = [benchmark_name, result.cycles, result.instr, ipc, mpki, result.wall_time, speed]

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
    parser.add_argument("--evlog", action="store_true", help="Write captured event logs")
    parser.add_argument("-b", "--backend", default="cocotb", choices=["cocotb", "pysim"], help="Simulation backend")
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Discard the generated Verilog and the built testbench",
    )
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=0,
        help="Number of benchmarks to run in parallel. Default: all cores",
    )
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

    if args.evlog:
        os.environ["__TRANSACTRON_EVLOG"] = "1"

    if args.clean:
        clean_build_artifacts(args.backend)

    jobs = len(os.sched_getaffinity(0)) if args.jobs == 0 else args.jobs

    success = run_benchmarks(benchmarks, args.backend, args.trace, jobs)
    if not success:
        print("Benchmark execution failed")
        sys.exit(1)

    ipcs = []

    results: dict[str, BenchmarkResult] = {}

    for name in benchmarks:
        with open(f"{str(test.benchmark.benchmark.results_dir)}/{name}.json", "r") as f:
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
