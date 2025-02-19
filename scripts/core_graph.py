#!/usr/bin/env python3

import pathlib
import sys
from argparse import ArgumentParser, FileType

par = ArgumentParser()
par.add_argument("-p", "--prune", action="store_true", help="ignore disconnected nodes")
par.add_argument("-f", "--format", default="elk", nargs="?")
par.add_argument("ofile", type=FileType("w"))

arg = par.parse_args()

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from coreblocks.params.genparams import GenParams  # noqa: E402
from transactron.graph import TracingFragment  # noqa: E402
from test.test_core import CoreTestElaboratable  # noqa: E402
from coreblocks.params.configurations import basic_core_config  # noqa: E402
from transactron.core import TransactionModule  # noqa: E402
from transactron.core.keys import TransactionManagerKey  # noqa: E402
from transactron.utils import DependencyManager, DependencyContext  # noqa: E402

with DependencyContext(DependencyManager()):
    gp = GenParams(basic_core_config)
    elaboratable = CoreTestElaboratable(gp)
    tm = TransactionModule(elaboratable)
    fragment = TracingFragment.get(tm, platform=None).prepare()

    core = fragment
    while not hasattr(core, "manager"):
        core = core._tracing_original  # type: ignore

    mgr = core.manager.get_dependency(TransactionManagerKey())  # type: ignore

    with arg.ofile as fp:
        graph = mgr.visual_graph(fragment)
        if arg.prune:
            graph.prune()
        graph.dump(fp, arg.format)
