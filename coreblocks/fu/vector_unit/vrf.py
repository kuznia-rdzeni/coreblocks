from amaranth import *
from coreblocks.transactions import Method, def_method
from coreblocks.transactions.lib import MemoryBank, Forwarder
from coreblocks.params import *
from coreblocks.params.vector_params import VectorParameters
from coreblocks.fu.vector_unit.v_layouts import VRFFragmentLayouts
from coreblocks.fu.vector_unit.v_register import VectorRegisterFragment
from coreblocks.utils.fifo import BasicFifo

__all__ = ["VRFFragment"]

class VRFFragment(Elaboratable):
    def __init__(self, *, gen_params: GenParams, v_params : VectorParameters):
        self.gen_params = gen_params
        self.v_params = v_params

        self.layout=VRFFragmentLayouts(self.gen_params, self.v_params)

        self.read_ports_count = 3
        self.read_req_list = [Method(i=self.layout.read_req) for _ in range(self.read_ports_count)]
        self.read_resp_list = [Method(i=self.layout.read_resp) for _ in range(self.read_ports_count)]
        self.write = Method()

        
        self.regs = [ VectorRegisterFragment(self.gen_params, self.v_params) for _ in range(self.v_params.vrp_count)]

        self.clear = MethodProduct([reg.clear for reg in self.regs])


    def elaborate(self, platform):
        m = Module()

        @def_method(m, self.write)
        def _(vrp_id, addr, data, mask):
            with m.Switch(vrp_id):
                for j in range(self.v_params.vrp_count):
                    with m.Case(j):
                        self.regs[j].write(m, data=data, addr=addr, mask=mask)


        for i in range(self.read_ports_count):
            @def_method(m, self.read_req_list[i])
            def _(vrp_id, elen_id):
                with m.Switch(vrp_id):
                    for j in range(self.v_params.vrp_count):
                        with m.Case(j):
                            self.regs[j].read_req(m, addr=elen_id)

            @def_method(m, self.read_resp_list[i])
            def _():
                with m.Switch(vrp_id):
                    for j in range(self.v_params.vrp_count):
                        with m.Case(j):
                            return self.regs[j].read_resp(m)
                    
