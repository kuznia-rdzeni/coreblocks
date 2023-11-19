#!/usr/bin/env python3

import sys
import os
import pathlib
import xml.etree.ElementTree as eT

FAILURE_TAG = "failure"
TOP_DIR = pathlib.Path(__file__).parent.parent
TEST_RESULTS_FILE = TOP_DIR.joinpath("test/regression/cocotb/results.xml")

if not os.path.exists(TEST_RESULTS_FILE):
    print("File not found: ", TEST_RESULTS_FILE)
    sys.exit(1)

tree = eT.parse(TEST_RESULTS_FILE)

if len(tree.findall(FAILURE_TAG)) > 0:
    print("Some regression tests failed")
    sys.exit(1)

print("All regression tests pass")
