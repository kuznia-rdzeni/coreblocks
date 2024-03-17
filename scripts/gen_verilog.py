#!/usr/bin/env python3

import os
import sys
import argparse

from amaranth import *
from amaranth.build import Platform
from amaranth import Module, Elaboratable


if __name__ == "__main__":
    parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, parent)

from coreblocks.params.genparams import GenParams
from coreblocks.peripherals.wishbone import WishboneSignature
from coreblocks.core import Core
from transactron import TransactionModule
from transactron.utils import DependencyManager, DependencyContext
from transactron.utils.gen import generate_verilog

from coreblocks.params.configurations import *

str_to_coreconfig: dict[str, CoreConfiguration] = {
    "basic": basic_core_config,
    "tiny": tiny_core_config,
    "full": full_core_config,
}


class Top(Elaboratable):
    def __init__(self, gen_params):
        self.gp: GenParams = gen_params

        self.wb_instr = WishboneSignature(self.gp.wb_params).create()
        self.wb_data = WishboneSignature(self.gp.wb_params).create()

    def elaborate(self, platform: Platform):
        m = Module()
        tm = TransactionModule(m, dependency_manager=DependencyContext.get())

        m.submodules.c = Core(gen_params=self.gp, wb_instr_bus=self.wb_instr, wb_data_bus=self.wb_data)

        return tm


def gen_verilog(core_config: CoreConfiguration, output_path: str):
    with DependencyContext(DependencyManager()):
        gp = GenParams(core_config)
        top = Top(gp)
        instr_ports: list[Signal] = [getattr(top.wb_instr, name) for name in top.wb_instr.signature.members]
        data_ports: list[Signal] = [getattr(top.wb_data, name) for name in top.wb_data.signature.members]
        for sig in instr_ports:
            sig.name = "wb_instr__" + sig.name
        for sig in data_ports:
            sig.name = "wb_data__" + sig.name

        verilog_text, gen_info = generate_verilog(top, instr_ports + data_ports)

        gen_info.encode(f"{output_path}.json")
        with open(output_path, "w") as f:
            f.write(verilog_text)


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
        "--strip-debug",
        action="store_true",
        help="Remove debugging signals. Default: %(default)s",
    )

    parser.add_argument(
        "-o", "--output", action="store", default="core.v", help="Output file path. Default: %(default)s"
    )

    args = parser.parse_args()

    os.environ["AMARANTH_verbose"] = "true" if args.verbose else "false"

    if args.config not in str_to_coreconfig:
        raise KeyError(f"Unknown config '{args.config}'")

    config = str_to_coreconfig[args.config]
    if args.strip_debug:
        config = config.replace(debug_signals=False)

    gen_verilog(config, args.output)


if __name__ == "__main__":
    main()
