#!/usr/bin/env python3

import os
import sys
import argparse

from amaranth.build import Platform
from amaranth.back import verilog
from amaranth import Module, Elaboratable, Record


class Top(Elaboratable):
    def __init__(self, gen_params):
        from coreblocks.params.genparams import GenParams
        from coreblocks.peripherals.wishbone import WishboneParameters, WishboneLayout

        self.gp: GenParams = gen_params

        self.wb_params = WishboneParameters(data_width=32, addr_width=30)

        wb_layout = WishboneLayout(self.wb_params).wb_layout

        # We create separate records, so the wire names in the generated Verilog are more descriptive.
        self.wb_instr = Record(wb_layout)
        self.wb_data = Record(wb_layout)

    def elaborate(self, platform: Platform):
        from coreblocks.core import Core
        from coreblocks.transactions import TransactionModule
        from coreblocks.peripherals.wishbone import WishboneMaster

        m = Module()
        tm = TransactionModule(m)

        wb_master_instr = WishboneMaster(wb_params=self.wb_params)
        wb_master_data = WishboneMaster(wb_params=self.wb_params)

        self.core = Core(gen_params=self.gp, wb_master_instr=wb_master_instr, wb_master_data=wb_master_data)

        m.d.comb += wb_master_instr.wbMaster.connect(self.wb_instr)
        m.d.comb += wb_master_data.wbMaster.connect(self.wb_data)

        m.submodules.wb_master_instr = wb_master_instr
        m.submodules.wb_master_data = wb_master_data
        m.submodules.c = self.core

        return tm


def gen_verilog(core_config):
    from coreblocks.params import GenParams
    from coreblocks.utils.utils import flatten_signals

    top = Top(GenParams(core_config))

    with open("core.v", "w") as f:
        signals = list(flatten_signals(top.wb_instr)) + list(flatten_signals(top.wb_data))

        f.write(verilog.convert(top, ports=signals, strip_internal_attrs=True))


def main():
    parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, parent)

    from coreblocks.params.configurations import basic_core_config, tiny_core_config

    configurations_str = {
        "basic": basic_core_config,
        "tiny": tiny_core_config,
    }

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
        help="Select core configuration."
        + f"Available configurations: {list(configurations_str.keys())}. Default: '%(default)s'",
    )

    args = parser.parse_args()

    os.environ["AMARANTH_verbose"] = "true" if args.verbose else "false"

    if args.config not in configurations_str:
        raise KeyError(f"Unknown config '{args.config}'")

    gen_verilog(configurations_str[args.config])


if __name__ == "__main__":
    main()
