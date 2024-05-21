#!/usr/bin/env python3

from collections.abc import Callable
import os
import sys
import argparse

from amaranth.build import Platform
from amaranth import *
from amaranth.lib.wiring import Flow, connect, flipped

if __name__ == "__main__":
    parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, parent)


from transactron.utils.dependencies import DependencyContext, DependencyManager
from transactron.utils import ModuleConnector
from transactron.utils._typing import AbstractInterface
from coreblocks.params.genparams import GenParams
from coreblocks.params.fu_params import FunctionalComponentParams
from coreblocks.core import Core
from coreblocks.func_blocks.fu.alu import ALUComponent
from coreblocks.func_blocks.fu.div_unit import DivComponent
from coreblocks.func_blocks.fu.mul_unit import MulComponent, MulType
from coreblocks.func_blocks.fu.shift_unit import ShiftUnitComponent
from coreblocks.func_blocks.fu.zbc import ZbcComponent
from coreblocks.func_blocks.fu.zbs import ZbsComponent
from transactron import TransactionModule
from transactron.lib import AdapterBase, AdapterTrans
from coreblocks.peripherals.wishbone import WishboneArbiter
from constants.ecp5_platforms import (
    ResourceBuilder,
    adapter_resources,
    append_resources,
    wishbone_resources,
    make_ecp5_platform,
)

from coreblocks.params.configurations import *

str_to_coreconfig: dict[str, CoreConfiguration] = {
    "basic": basic_core_config,
    "tiny": tiny_core_config,
    "full": full_core_config,
}


class InterfaceConnector(Elaboratable):
    def __init__(self, interface: AbstractInterface, name: str, number: int):
        self.interface = interface
        self.name = name
        self.number = number

    def elaborate(self, platform: Platform):
        m = Module()

        pins = platform.request(self.name, self.number)
        assert isinstance(pins, Record)

        for name in self.interface.signature.members:
            member = self.interface.signature.members[name]
            if member.flow == Flow.In:
                m.d.comb += getattr(pins, name).o.eq(getattr(self.interface, name))
            else:
                m.d.comb += getattr(self.interface, name).eq(getattr(pins, name).i)

        return m


class AdapterConnector(Elaboratable):
    def __init__(self, adapter: AdapterBase, number: int):
        self.adapter = adapter
        self.number = number

    @staticmethod
    def with_resources(adapter: AdapterBase, number: int):
        return AdapterConnector(adapter, number), adapter_resources(adapter, number)

    def elaborate(self, platform: Platform):
        m = Module()

        m.submodules.adapter = self.adapter

        pins = platform.request("adapter", self.number)
        assert isinstance(pins, Record)

        m.d.comb += self.adapter.en.eq(pins.en)
        m.d.comb += pins.done.eq(self.adapter.done)
        if "data_in" in pins.fields:
            m.d.comb += self.adapter.data_in.eq(pins.data_in)
        if "data_out" in pins.fields:
            m.d.comb += pins.data_out.eq(self.adapter.data_out)

        return m


UnitCore = Callable[[GenParams], tuple[ResourceBuilder, Elaboratable]]


class SynthesisCore(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params

    def elaborate(self, platform):
        m = Module()

        m.submodules.core = core = Core(gen_params=self.gen_params)
        m.submodules.wb_arbiter = wb_arbiter = WishboneArbiter(self.gen_params.wb_params, 2)
        m.submodules.wb_connector = InterfaceConnector(wb_arbiter.slave_wb, "wishbone", 0)

        connect(m, flipped(wb_arbiter.masters[0]), core.wb_instr)
        connect(m, flipped(wb_arbiter.masters[1]), core.wb_data)

        return m


def unit_core(gen_params: GenParams):
    resources = wishbone_resources(gen_params.wb_params)

    core = SynthesisCore(gen_params)

    return resources, TransactionModule(core, dependency_manager=DependencyContext.get())


def unit_fu(unit_params: FunctionalComponentParams):
    def unit(gen_params: GenParams):
        fu = unit_params.get_module(gen_params)

        issue_connector, issue_resources = AdapterConnector.with_resources(AdapterTrans(fu.issue), 0)
        accept_connector, accept_resources = AdapterConnector.with_resources(AdapterTrans(fu.accept), 1)

        resources = append_resources(issue_resources, accept_resources)

        module = ModuleConnector(fu=fu, issue_connector=issue_connector, accept_connector=accept_connector)

        return resources, TransactionModule(module, dependency_manager=DependencyContext.get())

    return unit


core_units = {
    "core": unit_core,
    "alu_basic": unit_fu(ALUComponent(False, False)),
    "alu_full": unit_fu(ALUComponent(True, True)),
    "mul_shift": unit_fu(MulComponent(MulType.SHIFT_MUL)),
    "mul_sequence": unit_fu(MulComponent(MulType.SEQUENCE_MUL)),
    "mul_recursive": unit_fu(MulComponent(MulType.RECURSIVE_MUL)),
    "div": unit_fu(DivComponent()),
    "shift_basic": unit_fu(ShiftUnitComponent(False)),
    "shift_full": unit_fu(ShiftUnitComponent(True)),
    "zbs": unit_fu(ZbsComponent()),
    "zbc": unit_fu(ZbcComponent()),
}


def synthesize(core_config: CoreConfiguration, platform: str, core: UnitCore):
    with DependencyContext(DependencyManager()):
        gen_params = GenParams(core_config)
        resource_builder, module = core(gen_params)

        if platform == "ecp5":
            make_ecp5_platform(resource_builder)().build(module)


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
        default="basic",
        help="Select core configuration. "
        + f"Available configurations: {', '.join(str_to_coreconfig.keys())}. Default: %(default)s",
    )

    parser.add_argument(
        "-u",
        "--unit",
        default="core",
        help="Select core unit." + f"Available units: {', '.join(core_units.keys())}. Default: %(default)s",
    )

    parser.add_argument(
        "--strip-debug",
        action="store_true",
        help="Remove debugging signals. Default: %(default)s",
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

    if args.unit not in core_units:
        raise KeyError(f"Unknown core unit '{args.unit}'")

    config = str_to_coreconfig[args.config]
    if args.strip_debug:
        config = config.replace(debug_signals=False)

    synthesize(config, args.platform, core_units[args.unit])


if __name__ == "__main__":
    main()
