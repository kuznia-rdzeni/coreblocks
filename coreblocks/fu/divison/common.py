from amaranth import *
from coreblocks.params import GenParams
from coreblocks.params.layouts import DivUnitLayouts
from coreblocks.transactions.core import Method


class DividerBase(Elaboratable):
    def __init__(self, gen: GenParams):
        self.gen = gen

        layout = gen.get(DivUnitLayouts)

        self.issue = Method(i=layout.issue)
        self.accept = Method(o=layout.accept)
