from amaranth import *
from coreblocks.transactions import Method, def_method
from coreblocks.transactions.lib import MemoryBank
from coreblocks.params import *
from coreblocks.params.vector_params import VectorParameters
from coreblocks.fu.vector_unit.v_layouts import RegisterLayouts

__all__ = ["ContinuousVectorRegister"]


class ContinuousVectorRegister(Elaboratable):
    def __init__(self, *, gen_params: GenParams, v_params : VectorParameters):
        self.gen_params = gen_params
        self.v_params = v_params

        self.layouts = RegisterLayouts(self.gen_params, self.v_params)

        self.banks = [MemoryBank(self.layouts.read_resp, self.v_params.register_bank_count)]

        self.read_req_methods = [ Method.like(bank.read_req) for bank in self.banks)]
        self.read_resp_methods = [ Method.like(bank.read_resp) for bank in self.banks)]
        self.write_methods = [ Method.like(bank.write) for bank in self.banks)]
        
    def elaborate(self, platform):
        m = Module()

        for i in range(self.v_params.register_bank_count):
            self.read_req_methods[i].proxy(self.banks[i].read_req)
            self.read_resp_methods[i].proxy(self.banks[i].read_resp)
            self.write_methods[i].proxy(self.banks[i].write)
