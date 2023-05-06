#!/usr/bin/env python3

import unittest
import argparse
import re
import sys
import os


def get_topdir_path():
    script_path = os.path.dirname(os.path.realpath(sys.argv[0]))
    return os.path.abspath(os.path.join(script_path, os.pardir))


def cd_to_topdir():
    os.chdir(get_topdir_path())


def load_tests():
    suite = unittest.TestLoader().discover(".")

    tests = {}

    def flatten(suite):
        if hasattr(suite, "__iter__"):
            for x in suite:
                flatten(x)
        else:
            tests[suite.id()] = suite

    flatten(suite)

    return suite, tests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-l", "--list", action="store_true", help="List all tests")
    parser.add_argument("-t", "--trace", action="store_true", help="Dump waveforms")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("-c", "--count", type=int, help="Start `c` first tests which math regexp")
    parser.add_argument("test_name", nargs="?")

    args = parser.parse_args()

    suite, tests = load_tests()

    if args.list:
        for name in tests:
            print(name)
        return

    verbosity_level = 2 if args.verbose else 1
    runner = unittest.TextTestRunner(verbosity=verbosity_level)

    if args.trace:
        os.environ["__COREBLOCKS_DUMP_TRACES"] = "1"

    if args.test_name:
        pattern = re.compile(args.test_name)
        matches = [test for name, test in tests.items() if pattern.search(name)]
        if not matches:
            print(f"Could not find test matching '{args.test_name}'")
            sys.exit(1)
        if args.count is not None:
            matches = matches[: args.count]

        to_run = unittest.TestSuite(matches)
    else:
        to_run = suite

    result = runner.run(to_run)

    sys.exit(not result.wasSuccessful())


if __name__ == "__main__":
    cd_to_topdir()
    main()
