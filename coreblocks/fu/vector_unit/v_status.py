from amaranth import *
from coreblocks.transactions import *
from coreblocks.params import *
from coreblocks.fu.vector_unit.utils import *


class VectorStatusUnit(Elaboratable):
    def __init__(self, gen_params : GenParams, v_params : VectorParameters):
        self.gen_params = gen_params
        self.v_params = v_params

    def elaborate(self, platform):
        m = TModule()


        return m
