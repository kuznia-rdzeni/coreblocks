from typing import Iterable

from amaranth import *

from coreblocks.params import GenParams, BlockComponentParams, DependencyManager
from coreblocks.params.dependencies import UnifierKey
from transactron import Method, TModule
from transactron.lib import MethodProduct, Collector
from coreblocks.utils.protocols import Unifier

__all__ = ["FuncBlocksUnifier"]


class FuncBlocksUnifier(Elaboratable):
    def __init__(
        self,
        *,
        gen_params: GenParams,
        blocks: Iterable[BlockComponentParams],
        extra_methods_required: Iterable[UnifierKey],
    ):
        self.rs_blocks = [(block.get_module(gen_params), block.get_optypes()) for block in blocks]
        self.extra_methods_required = extra_methods_required

        self.result_collector = Collector([block.get_result for block, _ in self.rs_blocks])
        self.get_result = self.result_collector.method

        self.update_combiner = MethodProduct([block.update for block, _ in self.rs_blocks])
        self.update = self.update_combiner.method

        self.clear_combiner = MethodProduct([block.clear for block, _ in self.rs_blocks])
        self.clear = self.clear_combiner.method

        self.unifiers: dict[str, Unifier] = {}
        self.extra_methods: dict[UnifierKey, Method] = {}

        connections = gen_params.get(DependencyManager)

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
        m = TModule()

        for n, (unit, _) in enumerate(self.rs_blocks):
            m.submodules[f"rs_block_{n}"] = unit

        m.submodules["result_collector"] = self.result_collector
        m.submodules["update_combiner"] = self.update_combiner
        m.submodules["clear_combiner"] = self.clear_combiner

        for name, unifier in self.unifiers.items():
            m.submodules[name] = unifier

        return m
