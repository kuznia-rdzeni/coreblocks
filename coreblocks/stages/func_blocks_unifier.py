from typing import Iterable

from amaranth import *

from coreblocks.params import GenParams, BlockComponentParams, ComponentConnections
from coreblocks.transactions import Method
from coreblocks.transactions.lib import MethodProduct, Collector


__all__ = ["FuncBlocksUnifier"]

from coreblocks.utils.protocols import Unifier


class FuncBlocksUnifier(Elaboratable):
    def __init__(
        self, *, gen_params: GenParams, blocks: Iterable[BlockComponentParams], connections: ComponentConnections
    ):
        self.rs_blocks = []

        for n, block in enumerate(blocks):
            self.rs_blocks.append(block.get_module(gen_params=gen_params, connections=connections))

        self.result_collector = Collector([block.get_result for block in self.rs_blocks])
        self.get_result = self.result_collector.method

        self.update_combiner = MethodProduct([block.update for block in self.rs_blocks])
        self.update = self.update_combiner.method

        self.unifiers: dict[str, Unifier] = {}
        self.extra_outputs: dict[str, Method] = {}

        for (key, output_methods) in connections.get_outputs().items():
            unifier_type = key.unifier()
            if unifier_type is not None and len(output_methods) > 1:
                unifier = unifier_type(output_methods)
                self.unifiers[key.method_name() + "_unifier"] = unifier
                self.extra_outputs[key.method_name()] = unifier.method
            elif len(output_methods) == 1:
                self.extra_outputs[key.method_name()] = output_methods[0]

    def __getattr__(self, item):
        return self.extra_outputs[item]

    def elaborate(self, platform):
        m = Module()

        for n, unit in enumerate(self.rs_blocks):
            m.submodules[f"rs_block_{n}"] = unit

        m.submodules["result_collector"] = self.result_collector
        m.submodules["update_combiner"] = self.update_combiner

        for (name, unifier) in self.unifiers.items():
            m.submodules[name] = unifier

        return m
