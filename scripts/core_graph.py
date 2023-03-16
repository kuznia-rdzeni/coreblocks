#!/usr/bin/env python3

import pathlib
import sys
from argparse import ArgumentParser, FileType

from coreblocks.params.genparams import GenParams
from coreblocks.transactions.graph import TracingFragment
from test.test_core import TestElaboratable
from coreblocks.params.configurations import basic_configuration

par = ArgumentParser()
par.add_argument("-p", "--prune", action="store_true", help="ignore disconnected nodes")
par.add_argument("-f", "--format", default="elk", nargs="?")
par.add_argument("ofile", type=FileType("w"))

arg = par.parse_args()

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

gp = GenParams("rv32i", basic_configuration)
elaboratable = TestElaboratable(gp)
fragment = TracingFragment.get(elaboratable, platform=None).prepare()

core = fragment
while not hasattr(core, "transactionManager"):
    core = core._tracing_original  # type: ignore

mgr = core.transactionManager  # type: ignore

with arg.ofile as fp:
    graph = mgr.visual_graph(fragment)
    if arg.prune:
        graph.prune()
    graph.dump(fp, arg.format)
