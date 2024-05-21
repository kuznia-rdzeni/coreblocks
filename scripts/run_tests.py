#!/usr/bin/env python3

import pytest
import argparse
import os
from pathlib import Path

topdir = Path(__file__).parent.parent


def cd_to_topdir():
    os.chdir(topdir)


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
    parser.add_argument(
        "-j", "--jobs", type=int, default=len(os.sched_getaffinity(0)), help="Start `j` jobs in parallel. Default: all"
    )
    parser.add_argument("--log-level", default="WARNING", action="store", help="Level of messages to display.")
    parser.add_argument("--log-filter", default=".*", action="store", help="Regexp used to filter out logs.")
    parser.add_argument("test_name", nargs="?")

    args = parser.parse_args()

    pytest_arguments = ["--max-worker-restart=1"]

    if args.trace:
        pytest_arguments.append("--coreblocks-traces")
    if args.profile:
        pytest_arguments.append("--coreblocks-profile")
    if args.test_name:
        pytest_arguments += [f"--coreblocks-test-name={args.test_name}"]
    if args.count:
        pytest_arguments += ["--coreblocks-test-count", str(args.count)]
    if args.list:
        pytest_arguments.append("--coreblocks-list")
    if args.jobs and not args.list:
        # To list tests we can not use xdist, because it doesn't support forwarding of stdout from workers.
        pytest_arguments += ["-n", str(args.jobs)]
    if args.all:
        pytest_arguments.append("--coreblocks-regression")
    if args.verbose:
        pytest_arguments.append("--verbose")
    if args.backend:
        pytest_arguments += [f"--coreblocks-backend={args.backend}"]
    if args.log_level:
        pytest_arguments += [f"--log-level={args.log_level}"]
    if args.log_filter:
        pytest_arguments += [f"--coreblocks-log-filter={args.log_filter}"]

    ret = pytest.main(pytest_arguments, [])

    exit(ret)


if __name__ == "__main__":
    cd_to_topdir()
    main()
