from collections.abc import Iterable

from amaranth import *

from coreblocks.params import GenParams, BlockComponentParams
from transactron import TModule, Methods
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

        self.get_result = [block.get_result for block, _ in self.rs_blocks]

        self.update = Methods(gen_params.announcement_superscalarity, i=self.rs_blocks[0][0].update.layout_in)

    def elaborate(self, platform):
        m = TModule()

        for n, (unit, _) in enumerate(self.rs_blocks):
            m.submodules[f"rs_block_{n}"] = unit

        for n in range(len(self.update)):
            self.update[n].provide(MethodProduct.create([block.update[n] for block, _ in self.rs_blocks]).use(m))

        return m
