from amaranth import *
from coreblocks.transactions import *
from coreblocks.transactions.lib import *
from coreblocks.params import *
from coreblocks.params.vector_params import VectorParameters
from coreblocks.fu.vector_unit.v_layouts import VRFFragmentLayouts
from coreblocks.fu.vector_unit.v_register import VectorRegisterBank

__all__ = ["VRFFragment"]


class VRFFragment(Elaboratable):
    def __init__(self, *, gen_params: GenParams, v_params: VectorParameters):
        self.gen_params = gen_params
        self.v_params = v_params

        self.layout = VRFFragmentLayouts(self.gen_params, self.v_params)

        self.read_ports_count = 3
        self.read_req_list = [Method(i=self.layout.read_req) for _ in range(self.read_ports_count)]
        self.read_resp_list = [
            Method(i=self.layout.read_resp_i, o=self.layout.read_resp_o) for _ in range(self.read_ports_count)
        ]
        self.write = Method()

        self.regs = [
            VectorRegisterBank(gen_params=self.gen_params, v_params=self.v_params)
            for _ in range(self.v_params.vrp_count)
        ]

        self.clear = MethodProduct([reg.clear for reg in self.regs])

    def elaborate(self, platform):
        m = TModule()

        @def_method(m, self.write)
        def _(vrp_id, addr, data, mask):
            with condition(vrp_id) as branch:
                for j in range(self.v_params.vrp_count):
                    with branch(j):
                        self.regs[j].write(m, data=data, addr=addr, mask=mask)

        for i in range(self.read_ports_count):

            @def_method(m, self.read_req_list[i])
            def _(vrp_id, elen_id):
                with condition(vrp_id) as branch:
                    for j in range(self.v_params.vrp_count):
                        with branch(j):
                            self.regs[j].read_req(m, addr=elen_id)

            @def_method(m, self.read_resp_list[i])
            def _(vrp_id):
                with condition(vrp_id) as branch:
                    for j in range(self.v_params.vrp_count):
                        with branch(j):
                            return self.regs[j].read_resp(m)
        return m
