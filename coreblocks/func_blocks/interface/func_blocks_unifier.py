from collections.abc import Iterable

from amaranth import *

from coreblocks.params import GenParams, BlockComponentParams
from transactron import TModule

__all__ = ["FuncBlocksUnifier"]


class FuncBlocksUnifier(Elaboratable):
    def __init__(
        self,
        *,
        gen_params: GenParams,
        blocks: Iterable[BlockComponentParams],
    ):
        self.rs_blocks = [(block.get_module(gen_params), block.get_optypes()) for block in blocks]

    def elaborate(self, platform):
        m = TModule()

        for n, (unit, _) in enumerate(self.rs_blocks):
            m.submodules[f"rs_block_{n}"] = unit

        return m
