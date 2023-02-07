from typing import Iterable

from amaranth import *

from coreblocks.params import GenParams, BlockComponentParams, ComponentDependencies
from coreblocks.transactions.lib import MethodProduct, Collector
from coreblocks.utils.protocols import LSUUnit, JumpUnit, FuncUnitsHolder


__all__ = ["FuncBlocksUnifier"]


class FuncBlocksUnifier(Elaboratable):
    def __init__(
        self, *, gen_params: GenParams, blocks: Iterable[BlockComponentParams], dependencies: ComponentDependencies
    ):
        self.rs_blocks = []

        for n, block in enumerate(blocks):
            self.rs_blocks.append(block.get_module(gen_params=gen_params, dependencies=dependencies))

        self.result_collector = Collector([block.get_result for block in self.rs_blocks])
        self.get_result = self.result_collector.get_single

        self.update_combiner = MethodProduct([block.update for block in self.rs_blocks])
        self.update = self.update_combiner.method

        branch_result_methods = [
            u.branch_result
            for b in self.rs_blocks
            if isinstance(b, FuncUnitsHolder)
            for u in b.func_units
            if isinstance(u, JumpUnit)
        ]

        self.branch_result_collector = None
        match branch_result_methods:
            case []:
                raise Exception("CPU without jumps")
            case [method]:
                self.branch_result = method
            case [*methods]:
                self.branch_result_collector = br_collector = Collector(methods)
                self.branch_result = br_collector.get_single

        commit_methods = [b.commit for b in self.rs_blocks if isinstance(b, LSUUnit)]

        self.commit_product = None
        match commit_methods:
            case []:
                raise Exception("CPU without side effects")
            case [method]:
                self.commit = method
            case [*methods]:
                self.commit_product = commit_product = MethodProduct(methods)
                self.commit = commit_product.method

    def elaborate(self, platform):
        m = Module()

        for n, unit in enumerate(self.rs_blocks):
            m.submodules[f"rs_block_{n}"] = unit

        m.submodules["result_collector"] = self.result_collector
        m.submodules["update_combiner"] = self.update_combiner

        if self.branch_result_collector is not None:
            m.submodules["branch_result_collector"] = self.branch_result_collector

        if self.commit_product is not None:
            m.submodules["commit_product"] = self.commit_product

        return m
