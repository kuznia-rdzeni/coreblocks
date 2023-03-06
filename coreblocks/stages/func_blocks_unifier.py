from typing import Iterable

from amaranth import *

from coreblocks.params import GenParams, BlockComponentParams, ComponentConnections
from coreblocks.params.fu_params import UnifierKey
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
        extra_methods_required: Iterable[UnifierKey],
    ):
        self.rs_blocks = [block.get_module(gen_params=gen_params, connections=connections) for block in blocks]
        self.extra_methods_required = extra_methods_required

        self.result_collector = Collector([block.get_result for block in self.rs_blocks])
        self.get_result = self.result_collector.method

        self.update_combiner = MethodProduct([block.update for block in self.rs_blocks])
        self.update = self.update_combiner.method

        self.unifiers: dict[str, Unifier] = {}
        self.extra_methods: dict[UnifierKey, Method] = {}

        for key in extra_methods_required:
            method, unifiers = connections.get_dependency(key)
            self.extra_methods[key] = method
            self.unifiers |= unifiers

    def get_extra_method(self, item: UnifierKey) -> Method:
        if item in self.extra_methods_required:
            return self.extra_methods[item]
        else:
            raise ValueError(f"Method {item} was not declared as required.")

    def elaborate(self, platform):
        m = Module()

        for n, unit in enumerate(self.rs_blocks):
            m.submodules[f"rs_block_{n}"] = unit

        m.submodules["result_collector"] = self.result_collector
        m.submodules["update_combiner"] = self.update_combiner

        for (name, unifier) in self.unifiers.items():
            m.submodules[name] = unifier

        return m
