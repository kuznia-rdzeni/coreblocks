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

        self.mask_read = Method()
        self.mask_write = Method()

        self.clear = Method()
        
        self.regs = [ VectorRegisterFragment(self.gen_params, self.v_params) for _ in range(self.v_params.vrp_count)]

        for i in range(self.read_ports_count):
            for j in range(i+1, self.read_ports_count):
                self.read_req_list[i].schedule_before(self.read_req_list[j])

    def elaborate(self, platform):
        m = Module()

        req_forwarders = [ Forwarder({"port_id", log2_int(self.read_ports_count)}) for _ in range(self.read_ports_count) ]

        for i in range(self.read_ports_count):
            m.submodules.forwarder[i]=req_forwarders[i]
            @def_method(m, self.read_req_list[i])
            def _(vrp_id, elen_id):
                port_id = Signal(range(self.read_ports_count), reset = i)

                for j in reverse(range(i)):
                    with m.If(self.read_req_list[j].run & (self.read_req_list[j].data_in.vrp_id == vrp_id) & (self.read_req_list[j].data_in.elen_id == elen_id)):
                        m.d.comb += port_id.eq(j)

                req_forwarders.write(m,port_id=port_id)

                with m.If(port_id==i):

