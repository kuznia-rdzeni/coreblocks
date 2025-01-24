#!/usr/bin/env python3

from collections.abc import Callable
import os
import sys
import argparse

from amaranth.build import Platform
from amaranth.build.res import PortGroup
from amaranth import *
from amaranth.lib.wiring import Component, Flow, Out, connect, flipped

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
from transactron.lib import AdapterTrans
from coreblocks.peripherals.wishbone import WishboneArbiter, WishboneInterface, WishboneSignature
from constants.ecp5_platforms import (
    ResourceBuilder,
    append_resources,
    signature_resources,
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

    @staticmethod
    def with_resources(interface: AbstractInterface, name: str, number: int):
        connector = InterfaceConnector(interface, name, number)
        resources = signature_resources(interface.signature, name, number)
        return connector, resources

    def elaborate(self, platform: Platform):
        m = Module()

        pins = platform.request(self.name, self.number)
        assert isinstance(pins, PortGroup)

        for hier_name, member, v in self.interface.signature.flatten(self.interface):
            name = "__".join(str(x) for x in hier_name)
            if member.flow == Flow.Out:
                m.d.comb += getattr(pins, name).o.eq(v)
            else:
                m.d.comb += v.eq(getattr(pins, name).i)

        return m


UnitCore = Callable[[GenParams], tuple[ResourceBuilder, Elaboratable]]


class SynthesisCore(Component):
    wb: WishboneInterface

    def __init__(self, gen_params: GenParams):
        super().__init__({"wb": Out(WishboneSignature(gen_params.wb_params))})
        self.gen_params = gen_params

    def elaborate(self, platform):
        m = Module()

        m.submodules.core = core = Core(gen_params=self.gen_params)
        m.submodules.wb_arbiter = wb_arbiter = WishboneArbiter(self.gen_params.wb_params, 2)

        connect(m, wb_arbiter.masters[0], core.wb_instr)
        connect(m, wb_arbiter.masters[1], core.wb_data)
        connect(m, flipped(self.wb), wb_arbiter.slave_wb)

        return m


def unit_core(gen_params: GenParams):
    core = SynthesisCore(gen_params)

    connector, resources = InterfaceConnector.with_resources(core, "wishbone", 0)

    module = ModuleConnector(core=core, connector=connector)

    return resources, TransactionModule(module, dependency_manager=DependencyContext.get())


def unit_fu(unit_params: FunctionalComponentParams):
    def unit(gen_params: GenParams):
        fu = unit_params.get_module(gen_params)
        issue_adapter = AdapterTrans(fu.issue)
        accept_adapter = AdapterTrans(fu.accept)

        issue_connector, issue_resources = InterfaceConnector.with_resources(issue_adapter, "adapter", 0)
        accept_connector, accept_resources = InterfaceConnector.with_resources(accept_adapter, "adapter", 1)

        resources = append_resources(issue_resources, accept_resources)

        module = ModuleConnector(
            fu=fu,
            issue_connector=issue_connector,
            accept_connector=accept_connector,
            issue_adapter=issue_adapter,
            accept_adapter=accept_adapter,
        )

        return resources, TransactionModule(module, dependency_manager=DependencyContext.get())

    return unit


core_units = {
    "core": unit_core,
    "alu_basic": unit_fu(ALUComponent(zba_enable=False, zbb_enable=False, zicond_enable=False)),
    "alu_full": unit_fu(ALUComponent(zba_enable=True, zbb_enable=True, zicond_enable=True)),
    "mul_shift": unit_fu(MulComponent(MulType.SHIFT_MUL)),
    "mul_sequence": unit_fu(MulComponent(MulType.SEQUENCE_MUL)),
    "mul_recursive": unit_fu(MulComponent(MulType.RECURSIVE_MUL)),
    "div": unit_fu(DivComponent()),
    "shift_basic": unit_fu(ShiftUnitComponent(zbb_enable=False)),
    "shift_full": unit_fu(ShiftUnitComponent(zbb_enable=True)),
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
