from amaranth import *
from coreblocks.transactions import *
from coreblocks.transactions.lib import *
from coreblocks.params import *
from coreblocks.utils import *
from coreblocks.fu.vector_unit.v_layouts import VRFFragmentLayouts
from coreblocks.fu.vector_unit.v_register import VectorRegisterBank

__all__ = ["VRFFragment"]


class VRFFragment(Elaboratable):
    """Fragment of vector register file

    This module provides a fragment of vector register file, which can be used
    in an architecture with a decentralised vector register file (e.g. fragments associated with lanes)
    or can be glued together to form a centralised one.

    If two `read_req` are issued at the same time to the same physical vector register and the same address, then
    this will take two cycles, because there is no support yet for detecting such collisions.

    Attributes
    ----------
    write : Method(one_caller = True)
        Method to write to the physical vector register. Use the `VRFFragmentLayouts.write` layout.
    read_req : list[Method(one_caller = True)]
        Methods that can be used to issue read requests to physical vector registers.
    read_resp : list[Method(one_caller = True)]
        Methods to receive the last issued read for the given physical vector register. This will
        always returns the last results, regardless of which `read_req` method was used to issue the request.
        So it is possible to issue a request using `read_req[0]` and receive results from it using
        `read_resp[1]`.
    """

    def __init__(self, *, gen_params: GenParams):
        self.gen_params = gen_params
        self.v_params = self.gen_params.v_params

        self.layout = VRFFragmentLayouts(self.gen_params)

        self.read_ports_count = 3
        self.read_req = [Method(i=self.layout.read_req) for _ in range(self.read_ports_count)]
        self.read_resp = [
            Method(i=self.layout.read_resp_i, o=self.layout.read_resp_o) for _ in range(self.read_ports_count)
        ]
        self.write = Method(i=self.layout.write)

        self.regs = [VectorRegisterBank(gen_params=self.gen_params) for _ in range(self.v_params.vrp_count)]

        self.clear_module = MethodProduct([reg.clear for reg in self.regs])
        self.clear = self.clear_module.method

    def elaborate(self, platform):
        m = TModule()

        m.submodules.regs = ModuleConnector(*self.regs)
        m.submodules.clear_product = self.clear_module

        @def_method(m, self.write)
        def _(vrp_id, addr, data, mask):
            for j in condition_switch(m, vrp_id, self.v_params.vrp_count, nonblocking=False):
                self.regs[j].write(m, data=data, addr=addr, mask=mask)

        @loop_def_method(m, self.read_req)
        def _(_, vrp_id, addr):
            for j in condition_switch(m, vrp_id, self.v_params.vrp_count, nonblocking=False):
                self.regs[j].read_req(m, addr=addr)

        @loop_def_method(m, self.read_resp)
        def _(_, vrp_id):
            out = Record(self.layout.read_resp_o)
            for j in condition_switch(m, vrp_id, self.v_params.vrp_count, nonblocking=False):
                m.d.comb += assign(out, self.regs[j].read_resp(m), fields=AssignType.ALL)
            return out

        return m
