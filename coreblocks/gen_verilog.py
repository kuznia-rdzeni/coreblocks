#!/usr/bin/env python3

import os
import argparse
from importlib.machinery import SourceFileLoader
from importlib.metadata import version

from coreblocks.params.genparams import GenParams
from coreblocks.core import Core
from coreblocks.socks.socks import Socks
from coreblocks.params.core_configuration import CoreConfiguration
from coreblocks.params import configurations

from transactron import TransactronContextComponent
from transactron.utils import DependencyManager, DependencyContext
from transactron.utils.gen import generate_verilog


def gen_verilog(
    core_config: CoreConfiguration, output_path: str, *, wrap_socks: bool = False, enable_vivado_hacks: bool = False
):
    with DependencyContext(DependencyManager()):
        gp = GenParams(core_config)
        core = Core(gen_params=gp)
        if wrap_socks:
            core = Socks(core, core_gen_params=gp)

        top = TransactronContextComponent(core, dependency_manager=DependencyContext.get())

        # use known working yosys version shipped with amaranth by default
        if "AMARANTH_USE_YOSYS" not in os.environ:
            os.environ["AMARANTH_USE_YOSYS"] = "builtin"

        enable_hacks = []
        if enable_vivado_hacks:
            enable_hacks.append("fixup_vivado_transparent_memories")

        verilog_text, gen_info = generate_verilog(top, enable_hacks=enable_hacks)

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
        + f"Available configurations: {', '.join(configurations.__all__)}. Default: %(default)s",
    )

    parser.add_argument(
        "-f",
        "--configfile",
        action="store",
        default=None,
        help="Select custom config file for core configuration. "
        + "File should contain coreblocks.params.core_configuration.CoreConfiguration instances as global variables",
    )

    parser.add_argument(
        "--strip-debug",
        action="store_true",
        help="Remove debugging signals. Default: %(default)s",
    )

    parser.add_argument(
        "--with-socks",
        action="store_true",
        help="Wrap Coreblocks in CoreSoCks providing additional memory-mapped or CSR peripherals",
    )

    parser.add_argument(
        "--enable-vivado-hacks",
        action="store_true",
        help="Enable elaboration and generation hacks for Vivado toolchain",
    )

    parser.add_argument("--reset-pc", action="store", default="0x0", help="Set core reset address")

    parser.add_argument(
        "-o", "--output", action="store", default="core.v", help="Output file path. Default: %(default)s"
    )

    args = parser.parse_args()

    os.environ["AMARANTH_verbose"] = "true" if args.verbose else "false"

    configfile = SourceFileLoader("configfile", args.configfile).load_module() if args.configfile else configurations

    if args.config not in dir(configfile):
        raise KeyError(f"Unknown config '{args.config}'")

    config = getattr(configfile, args.config)
    assert isinstance(config, CoreConfiguration)

    if args.strip_debug:
        config = config.replace(debug_signals=False)

    assert args.reset_pc[:2] == "0x", "Expected hex number as --reset-pc"
    config = config.replace(start_pc=int(args.reset_pc[2:], base=16))

    print(f"Coreblocks {version('coreblocks')}, {args.config} core configuration, generating verilog to {args.output}")

    gen_verilog(config, args.output, wrap_socks=args.with_socks, enable_vivado_hacks=args.enable_vivado_hacks)


if __name__ == "__main__":
    main()
