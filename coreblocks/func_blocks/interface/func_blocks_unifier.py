from collections.abc import Iterable

from amaranth import *

from coreblocks.params import GenParams, BlockComponentParams
from transactron import TModule
from transactron.lib import MethodProduct

__all__ = ["FuncBlocksUnifier"]


class FuncBlocksUnifier(Elaboratable):
    def __init__(
        self,
        *,
        gen_params: GenParams,
        blocks: Iterable[BlockComponentParams],
    ):
        self.rs_blocks = [(block.get_module(gen_params), block.get_optypes()) for block in blocks]

        self.update_combiner = MethodProduct([block.update for block, _ in self.rs_blocks])
        self.update = self.update_combiner.method

    def elaborate(self, platform):
        m = TModule()

        for n, (unit, _) in enumerate(self.rs_blocks):
            m.submodules[f"rs_block_{n}"] = unit

        m.submodules["update_combiner"] = self.update_combiner

        return m
