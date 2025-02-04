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
from transactron import TransactionComponent
from transactron.utils import DependencyManager, DependencyContext
from transactron.utils.gen import generate_verilog

from coreblocks.params.configurations import *

str_to_coreconfig: dict[str, CoreConfiguration] = {
    "basic": basic_core_config,
    "tiny": tiny_core_config,
    "full": full_core_config,
}


def gen_verilog(core_config: CoreConfiguration, output_path: str):
    with DependencyContext(DependencyManager()):
        gp = GenParams(core_config)
        top = TransactionComponent(Core(gen_params=gp), dependency_manager=DependencyContext.get())

        verilog_text, gen_info = generate_verilog(top)

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

    parser.add_argument("--reset-pc", action="store", default="0x0", help="Set core reset address")

    args = parser.parse_args()

    os.environ["AMARANTH_verbose"] = "true" if args.verbose else "false"

    if args.config not in str_to_coreconfig:
        raise KeyError(f"Unknown config '{args.config}'")

    config = str_to_coreconfig[args.config]
    if args.strip_debug:
        config = config.replace(debug_signals=False)

    assert args.reset_pc[:2] == "0x", "Expected hex number as --reset-pc"
    config = config.replace(start_pc=int(args.reset_pc[2:], base=16))

    gen_verilog(config, args.output)


if __name__ == "__main__":
    main()
