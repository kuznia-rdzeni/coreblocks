#!/usr/bin/env python3

import os
import sys
import argparse

from amaranth import *


if __name__ == "__main__":
    parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, parent)

from coreblocks.params.genparams import GenParams
from coreblocks.core import Core
from coreblocks.socks.socks import Socks
from transactron import TransactronContextComponent
from transactron.utils import DependencyManager, DependencyContext
from transactron.utils.gen import generate_verilog

from coreblocks.params.configurations import *

str_to_coreconfig: dict[str, CoreConfiguration] = {
    "basic": basic_core_config,
    "tiny": tiny_core_config,
    "small_linux": small_linux_config,
    "full": full_core_config,
}


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
        + f"Available configurations: {', '.join(list(str_to_coreconfig.keys()))}. Default: %(default)s",
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

    if args.config not in str_to_coreconfig:
        raise KeyError(f"Unknown config '{args.config}'")

    config = str_to_coreconfig[args.config]
    if args.strip_debug:
        config = config.replace(debug_signals=False)

    assert args.reset_pc[:2] == "0x", "Expected hex number as --reset-pc"
    config = config.replace(start_pc=int(args.reset_pc[2:], base=16))

    gen_verilog(config, args.output, wrap_socks=args.with_socks, enable_vivado_hacks=args.enable_vivado_hacks)


if __name__ == "__main__":
    main()
