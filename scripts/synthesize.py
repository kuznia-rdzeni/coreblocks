#!/usr/bin/env python3

import os
import sys
import argparse

from amaranth.build import Platform
from amaranth import Module, Elaboratable


if __name__ == "__main__":
    parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, parent)


from coreblocks.params.genparams import GenParams
from coreblocks.core import Core
from coreblocks.transactions import TransactionModule
from coreblocks.peripherals.wishbone import WishboneArbiter, WishboneBus
from constants.ecp5_platforms import make_ecp5_platform

from coreblocks.params.configurations import *

str_to_coreconfig: dict[str, CoreConfiguration] = {
    "basic": basic_core_config,
    "tiny": tiny_core_config,
    "full": full_core_config,
}


class TestElaboratable(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params

    def elaborate(self, platform: Platform):
        m = Module()
        tm = TransactionModule(m)

        self.wb_instr = WishboneBus(self.gen_params.wb_params)
        self.wb_data = WishboneBus(self.gen_params.wb_params)

        self.core = Core(gen_params=self.gen_params, wb_instr_bus=self.wb_instr, wb_data_bus=self.wb_data)

        # Combine Wishbone buses with an arbiter
        wb = WishboneBus(self.gen_params.wb_params)
        self.wb_arbiter = WishboneArbiter(wb, [self.wb_instr, self.wb_data])

        # Request platform pins
        wb_pins = platform.request("wishbone", 0)

        # Connect pins to the core
        m.d.comb += wb.connect(wb_pins)

        m.submodules.wb_arbiter = self.wb_arbiter
        m.submodules.c = self.core

        return tm


def synthesize(core_config: CoreConfiguration, platform: str):
    gen_params = GenParams(core_config)

    if platform == "ecp5":
        make_ecp5_platform(gen_params.wb_params)().build(TestElaboratable(gen_params))


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
        "-c",
        "--config",
        action="store",
        default="basic",
        help="Select core configuration. "
        + f"Available configurations: {', '.join(list(str_to_coreconfig.keys()))}. Default: %(default)s",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enables verbose output. Default: %(default)s",
    )

    args = parser.parse_args()

    os.environ["AMARANTH_verbose"] = "true" if args.verbose else "false"

    if args.config not in str_to_coreconfig:
        raise KeyError(f"Unknown config '{args.config}'")

    synthesize(str_to_coreconfig[args.config], args.platform)


if __name__ == "__main__":
    main()
