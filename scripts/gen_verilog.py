#!/usr/bin/env python3

import os
import sys
import argparse

from amaranth.build import Platform
from amaranth.back import verilog
from amaranth import Module, Elaboratable, Record, Signal


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


def record_to_signals(record: Record) -> list[Signal]:
    return list(record.fields.values())


def gen_verilog():
    from coreblocks.params.genparams import GenParams
    from coreblocks.params.configurations import basic_configuration

    top = Top(GenParams("rv32i", basic_configuration))

    with open("core.v", "w") as f:
        signals = record_to_signals(top.wb_instr) + record_to_signals(top.wb_data)

        f.write(verilog.convert(top, ports=signals, strip_internal_attrs=True))


def main():
    parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, parent)

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
