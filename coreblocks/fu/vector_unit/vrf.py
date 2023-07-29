from amaranth import *
from amaranth.utils import *
from coreblocks.transactions import *
from coreblocks.transactions.lib import *
from coreblocks.params import *
from coreblocks.utils import *
from coreblocks.fu.vector_unit.v_layouts import VRFFragmentLayouts
from coreblocks.fu.vector_unit.v_register import VectorRegisterBank
from coreblocks.utils.fifo import *

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
    initialise_list : list[Method]
        List with initialisation methods for register banks, `initialise_list[i]` initialises
        bank of `i`-th register.
    """

    def __init__(self, *, gen_params: GenParams):
        self.gen_params = gen_params
        self.v_params = self.gen_params.v_params

        self.layout = VRFFragmentLayouts(self.gen_params)

        self.read_ports_count = 4
        self.read_req = [Method(i=self.layout.read_req) for _ in range(self.read_ports_count)]
        self.read_resp = [ Method(o=self.layout.read_resp_o) for _ in range(self.read_ports_count) ]
        self.write = Method(i=self.layout.write)

        self.regs = [VectorRegisterBank(gen_params=self.gen_params) for _ in range(self.v_params.vrp_count)]

        self.clear_module = MethodProduct([reg.clear for reg in self.regs])
        self.clear = self.clear_module.method
        self.initialise_list = [reg.initialise for reg in self.regs]

    def elaborate(self, platform):
        m = TModule()

        m.submodules.regs = ModuleConnector(*self.regs)
        m.submodules.clear_product = self.clear_module

        fifos_write = [BasicFifo(self.regs[0].write.data_in.layout, 2) for j in range(self.v_params.vrp_count)]
        fifos_req = [[BasicFifo(self.regs[0].read_req.data_in.layout, 2) for j in range(self.v_params.vrp_count)] for i in range(self.read_ports_count)] 
        fifos_resp = [BasicFifo(self.regs[0].read_resp.data_out.layout, 2) for i in range(self.read_ports_count)] 
        fifos_resp_id = [BasicFifo([("port_id", log2_int(self.read_ports_count, False))], 2) for j in range(self.v_params.vrp_count)]

        m.submodules.fifos_write = ModuleConnector(ModuleConnector(*fifos_write))
        m.submodules.fifos_resp_id = ModuleConnector(ModuleConnector(*fifos_resp_id))
        m.submodules.fifos_req = ModuleConnector(*list(map(lambda x: ModuleConnector(*x), fifos_req)))
        m.submodules.fifos_resp = ModuleConnector(*fifos_resp)
        m.submodules.connect_writes = ModuleConnector(*[ConnectTrans(fifos_write[j].read, self.regs[j].write) for j in range(self.v_params.vrp_count)])

        for i in range(self.read_ports_count):
            for j in range(self.v_params.vrp_count):
                with Transaction().body(m):
                    arg = fifos_req[i][j].read(m)
                    self.regs[j].read_req(m, arg)
                    fifos_resp_id[j].write(m, port_id = i)

        for i in range(self.read_ports_count):
            for j in range(self.v_params.vrp_count):
                with Transaction().body(m, request = (fifos_resp_id[j].head == i)):
                    id = fifos_resp_id[j].read(m)
                    data = self.regs[j].read_resp(m)
                    fifos_resp[i].write(m, data)

        @def_method(m, self.write)
        def _(vrp_id, addr, data, valid_mask):
            with m.Switch(vrp_id):
                for j in range(self.v_params.vrp_count):
                    with m.Case(j):
                        fifos_write[j].write(m, data=data, addr=addr, valid_mask=valid_mask)

        @loop_def_method(m, self.read_req)
        def _(i, arg):
            with m.Switch(arg.vrp_id):
                for j in range(self.v_params.vrp_count):
                    with m.Case(j):
                        fifos_req[i][j].write(m, addr = arg.addr)


        @loop_def_method(m, self.read_resp)
        def _(i):
            return fifos_resp[i].read(m)

        return m
