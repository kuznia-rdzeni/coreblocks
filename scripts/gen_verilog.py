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
from coreblocks.transactions import TransactionModule
from coreblocks.params.configurations import basic_configuration
from coreblocks.utils.utils import flatten_signals


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


def gen_verilog():
    top = Top(GenParams("rv32i", basic_configuration))

    with open("core.v", "w") as f:
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

    args = parser.parse_args()

    os.environ["AMARANTH_verbose"] = "true" if args.verbose else "false"

    gen_verilog()


if __name__ == "__main__":
    main()
