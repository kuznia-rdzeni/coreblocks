from typing import Iterable

from amaranth import *

from coreblocks.params import GenParams, BlockComponentParams, ComponentConnections, blocks_method_unifiers
from coreblocks.transactions import Method
from coreblocks.transactions.lib import MethodProduct, Collector

__all__ = ["FuncBlocksUnifier"]

from coreblocks.utils.protocols import Unifier


class FuncBlocksUnifier(Elaboratable):
    def __init__(
        self,
        *,
        gen_params: GenParams,
        blocks: Iterable[BlockComponentParams],
        connections: ComponentConnections,
        extra_methods_required: Iterable[str],
    ):
        self.rs_blocks = []
        self.extra_methods_required = extra_methods_required

        for n, block in enumerate(blocks):
            self.rs_blocks.append(block.get_module(gen_params=gen_params, connections=connections))

        self.result_collector = Collector([block.get_result for block in self.rs_blocks])
        self.get_result = self.result_collector.method

        self.update_combiner = MethodProduct([block.update for block in self.rs_blocks])
        self.update = self.update_combiner.method

        self.unifiers: dict[str, Unifier] = {}
        self.extra_methods: dict[str, Method] = {}

        for name in extra_methods_required:
            if name not in connections.registered_methods or connections.registered_methods[name] == []:
                raise Exception(f"Method {name} is not provided by FU configuration.")
            elif len(connections.registered_methods[name]) == 1:
                self.extra_methods[name] = connections.registered_methods[name][0]
            else:
                unifier = blocks_method_unifiers[name](connections.registered_methods[name])
                self.unifiers[name + "_unifier"] = unifier
                self.extra_methods[name] = unifier.method

    def __getattr__(self, item: str) -> Method:
        if item in self.extra_methods_required:
            return self.extra_methods[item]
        else:
            raise Exception(f"Method {item} was not declared as required.")

    def elaborate(self, platform):
        m = Module()

        for n, unit in enumerate(self.rs_blocks):
            m.submodules[f"rs_block_{n}"] = unit

        m.submodules["result_collector"] = self.result_collector
        m.submodules["update_combiner"] = self.update_combiner

        for (name, unifier) in self.unifiers.items():
            m.submodules[name] = unifier

        return m
