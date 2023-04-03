#!/usr/bin/env python3

import os
import sys
import argparse

from amaranth.build import Platform
from amaranth import Module, Elaboratable, Cat

from typing import Optional


class TestElaboratable(Elaboratable):
    def __init__(self, gen_params, io_pins: int, instr_mem: list[int] = [], data_mem: Optional[list[int]] = None):
        from coreblocks.params.genparams import GenParams

        self.gp: GenParams = gen_params
        self.io_pins: int = io_pins
        self.instr_mem = instr_mem
        if data_mem is None:
            self.data_mem = [0] * (2**10)
        else:
            self.data_mem = data_mem

    def elaborate(self, platform: Platform):
        from coreblocks.core import Core
        from coreblocks.transactions import TransactionModule
        from coreblocks.peripherals.wishbone import WishboneMaster, WishboneMemorySlave, WishboneParameters

        m = Module()
        tm = TransactionModule(m)
        wb_params = WishboneParameters(data_width=32, addr_width=30)

        self.wb_master = WishboneMaster(wb_params=wb_params)
        self.wb_mem_slave = WishboneMemorySlave(wb_params=wb_params, width=32, depth=32, init=self.instr_mem)

        self.wb_master_data = WishboneMaster(wb_params=wb_params)
        self.wb_mem_slave_data = WishboneMemorySlave(
            wb_params=wb_params, width=32, depth=len(self.data_mem), init=self.data_mem
        )

        self.core = Core(gen_params=self.gp, wb_master_instr=self.wb_master, wb_master_data=self.wb_master_data)

        m.d.comb += self.wb_master.wbMaster.connect(self.wb_mem_slave.bus)
        m.d.comb += self.wb_master_data.wbMaster.connect(self.wb_mem_slave_data.bus)

        # Request platform pins
        data_out_pins = Cat(platform.request("data_out", 0).o)

        # Make sure the number of pins matches the number of inputs/outputs
        assert len(data_out_pins) == len(Cat(self.core.announcement.debug_signals()))

        # Connect pins to the core
        m.d.comb += Cat(data_out_pins).eq(Cat(self.core.announcement.debug_signals()))

        m.submodules.wb_master = self.wb_master
        m.submodules.wb_master_data = self.wb_master_data
        m.submodules.wb_mem_slave = self.wb_mem_slave
        m.submodules.wb_mem_slave_data = self.wb_mem_slave_data
        m.submodules.c = self.core

        return tm


def synthesize(platform: str):
    from coreblocks.params.genparams import GenParams
    from constants.ecp5_platforms import ECP5BG381Platform
    from coreblocks.params.configurations import BasicCoreConfig

    gp = GenParams(BasicCoreConfig())

    if platform == "ecp5":
        ECP5BG381Platform().build(TestElaboratable(gen_params=gp, io_pins=6))


def main():
    parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, parent)

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
