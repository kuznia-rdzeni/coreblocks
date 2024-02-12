#!/usr/bin/env python3

import os
import sys
import argparse

from amaranth.build import Platform
from amaranth.back import verilog
from amaranth import Module, Elaboratable
from amaranth.hdl import ir
from amaranth.hdl.ast import SignalDict

if __name__ == "__main__":
    parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, parent)

from coreblocks.params.genparams import GenParams
from coreblocks.peripherals.wishbone import WishboneBus
from coreblocks.core import Core
from coreblocks.utils.gen_info import *
from transactron.lib.metrics import HardwareMetricsManager
from transactron import TransactionModule
from transactron.utils import flatten_signals, DependencyManager, DependencyContext

from coreblocks.params.configurations import *

str_to_coreconfig: dict[str, CoreConfiguration] = {
    "basic": basic_core_config,
    "tiny": tiny_core_config,
    "full": full_core_config,
}


class Top(Elaboratable):
    def __init__(self, gen_params):
        self.gp: GenParams = gen_params

        self.wb_instr = WishboneBus(self.gp.wb_params, name="wb_instr")
        self.wb_data = WishboneBus(self.gp.wb_params, name="wb_data")

    def elaborate(self, platform: Platform):
        m = Module()
        tm = TransactionModule(m, dependency_manager=DependencyContext.get())

        m.submodules.c = Core(gen_params=self.gp, wb_instr_bus=self.wb_instr, wb_data_bus=self.wb_data)

        return tm


def escape_verilog_identifier(identifier: str) -> str:
    """
    Escapes a Verilog identifier according to the language standard.

    From IEEE Std 1364-2001 (IEEE Standard Verilog® Hardware Description Language)

    "2.7.1 Escaped identifiers

    Escaped identifiers shall start with the backslash character and end with white
    space (space, tab, newline). They provide a means of including any of the printable ASCII
    characters in an identifier (the decimal values 33 through 126, or 21 through 7E in hexadecimal)."
    """

    # The standard says how to escape a identifier, but not when. So this is
    # a non-exhaustive list of characters that Yosys escapes (it is used
    # by Amaranth when generating Verilog code).
    characters_to_escape = [".", "$"]

    for char in characters_to_escape:
        if char in identifier:
            # Note the intentional space at the end.
            return f"\\{identifier} "

    return identifier


def collect_metric_locations(gen_params: GenParams, name_map: SignalDict) -> dict[str, CoreMetricLocation]:
    if not gen_params.debug_signals_enabled:
        return {}

    core_metrics_location: dict[str, CoreMetricLocation] = {}

    # Collect information about the location of metric registers in the generated code.
    metrics_manager = HardwareMetricsManager()
    for metric_name, metric in metrics_manager.get_metrics().items():
        metric_loc = CoreMetricLocation()
        for reg_name in metric.regs:
            signal_location = name_map[metrics_manager.get_register_value(metric_name, reg_name)]

            # Amaranth escapes identifiers when generating Verilog code, but returns non-escaped identifiers
            # in the name map, so we need to take care of it manually.
            signal_location = [escape_verilog_identifier(component) for component in signal_location]

            metric_loc.regs[reg_name] = signal_location

        core_metrics_location[metric_name] = metric_loc

    return core_metrics_location


def gen_verilog(core_config: CoreConfiguration, output_path: str):
    with DependencyContext(DependencyManager()):
        gp = GenParams(core_config)
        top = Top(gp)

        ports = list(flatten_signals(top.wb_instr)) + list(flatten_signals(top.wb_data))

        fragment = ir.Fragment.get(top, platform=None).prepare(ports=ports)
        verilog_text, name_map = verilog.convert_fragment(
            fragment, name="top", emit_src=True, strip_internal_attrs=True
        )

        gen_info = CoreGenInfo(core_metrics_location=collect_metric_locations(gp, name_map))  # type: ignore
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
