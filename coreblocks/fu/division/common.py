from amaranth import *
from coreblocks.params import GenParams
from coreblocks.params.layouts import DivUnitLayouts
from transactron.core import Method


class DividerBase(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params

        layout = gen_params.get(DivUnitLayouts)

        self.issue = Method(i=layout.issue)
        self.accept = Method(o=layout.accept)
        self.clear = Method()
