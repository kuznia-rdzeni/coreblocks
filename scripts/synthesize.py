#!/usr/bin/env python3

import os
import sys
import argparse

from amaranth.build import Platform
from amaranth import Module, Elaboratable
from amaranth.hdl.rec import Record


if __name__ == "__main__":
    parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, parent)


from coreblocks.params.genparams import GenParams
from coreblocks.core import Core
from coreblocks.transactions import TransactionModule
from coreblocks.peripherals.wishbone import WishboneArbiter, WishboneMaster, WishboneParameters
from coreblocks.params.configurations import basic_configuration


class TestElaboratable(Elaboratable):
    def __init__(self, gen_params: GenParams, wb_params: WishboneParameters):
        self.gen_params = gen_params
        self.wb_params = wb_params

    def elaborate(self, platform: Platform):
        m = Module()
        tm = TransactionModule(m)

        self.wb_master_instr = WishboneMaster(wb_params=self.wb_params)
        self.wb_master_data = WishboneMaster(wb_params=self.wb_params)

        self.core = Core(
            gen_params=self.gen_params, wb_master_instr=self.wb_master_instr, wb_master_data=self.wb_master_data
        )

        # Combine Wishbone buses with an arbiter
        wb = Record.like(self.wb_master_instr.wbMaster)
        self.wb_arbiter = WishboneArbiter(wb, [self.wb_master_instr.wbMaster, self.wb_master_data.wbMaster])

        # Request platform pins
        wb_pins = platform.request("wishbone", 0)

        # Connect pins to the core
        m.d.comb += wb.connect(wb_pins)

        m.submodules.wb_master_instr = self.wb_master_instr
        m.submodules.wb_master_data = self.wb_master_data
        m.submodules.wb_arbiter = self.wb_arbiter
        m.submodules.c = self.core

        return tm


def synthesize(platform: str):
    from constants.ecp5_platforms import make_ecp5_platform

    gen_params = GenParams("rv32i", basic_configuration)
    wb_params = WishboneParameters(data_width=32, addr_width=30)

    if platform == "ecp5":
        make_ecp5_platform(wb_params)().build(TestElaboratable(gen_params, wb_params))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-p",
        "--platform",
        default="ecp5",
        choices=["ecp5"],
        help="Selects platform to synthesize circuit on. Default: %(default)s",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enables verbose output. Default: %(default)s",
    )

    args = parser.parse_args()

    os.environ["AMARANTH_verbose"] = "true" if args.verbose else "false"

    synthesize(args.platform)


if __name__ == "__main__":
    main()
