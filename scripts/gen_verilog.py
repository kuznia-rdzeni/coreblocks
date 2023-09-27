#!/usr/bin/env python3

import os
import sys
import argparse

from amaranth.build import Platform
from amaranth.back import verilog
from amaranth import Module, Elaboratable

if __name__ == "__main__":
    parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, parent)

from coreblocks.params.genparams import GenParams
from coreblocks.peripherals.wishbone import WishboneBus
from coreblocks.core import Core
from transactron import TransactionModule
from coreblocks.utils.utils import flatten_signals

from coreblocks.params.configurations import *

str_to_coreconfig: dict[str, CoreConfiguration] = {
    "basic": basic_core_config,
    "tiny": tiny_core_config,
    "full": full_core_config,
}


class Top(Elaboratable):
    def __init__(self, gen_params):
        self.gp: GenParams = gen_params

        self.wb_instr = WishboneBus(self.gp.wb_params, name="wb_instr")
        self.wb_data = WishboneBus(self.gp.wb_params, name="wb_data")

    def elaborate(self, platform: Platform):
        m = Module()
        tm = TransactionModule(m)

        m.submodules.c = Core(gen_params=self.gp, wb_instr_bus=self.wb_instr, wb_data_bus=self.wb_data)

        return tm


def gen_verilog(core_config: CoreConfiguration, output_path):
    top = Top(GenParams(core_config))

    with open(output_path, "w") as f:
        signals = list(flatten_signals(top.wb_instr)) + list(flatten_signals(top.wb_data))

        f.write(verilog.convert(top, ports=signals, strip_internal_attrs=True))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enables verbose output. Default: %(default)s",
    )

    parser.add_argument(
        "-c",
        "--config",
        action="store",
        default="basic",
        help="Select core configuration. "
        + f"Available configurations: {', '.join(list(str_to_coreconfig.keys()))}. Default: %(default)s",
    )

    parser.add_argument(
        "-o", "--output", action="store", default="core.v", help="Output file path. Default: %(default)s"
    )

    args = parser.parse_args()

    os.environ["AMARANTH_verbose"] = "true" if args.verbose else "false"

    if args.config not in str_to_coreconfig:
        raise KeyError(f"Unknown config '{args.config}'")

    gen_verilog(str_to_coreconfig[args.config], args.output)


if __name__ == "__main__":
    main()
