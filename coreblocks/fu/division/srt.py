# from amaranth import *
from coreblocks.fu.division.common import DividerBase
from coreblocks.params import GenParams


class SRTDivider(DividerBase):
    def __init__(self, gen: GenParams):
        super().__init__(gen)

    def elaborate(self, platform):
        # m = Module()
        pass
