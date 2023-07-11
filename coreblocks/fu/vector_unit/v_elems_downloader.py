from amaranth import *
from coreblocks.transactions import *
from coreblocks.transactions.lib import *
from coreblocks.utils import *
from coreblocks.params import *
from coreblocks.utils.fifo import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.fu.vector_unit.vrs import *
from coreblocks.structs_common.scoreboard import *

__all__ = ["VectorElemsDownloader"]

class VectorElemsDownloader(Elaboratable):
    def __init__(self, gen_params : GenParams, read_req_list : list[Method], read_resp_list : list[Method], send_to_fu : Method):
        self.gen_params = gen_params
        self.v_params = self.gen_params.v_params
        self.read_req_list = [NotMethod(m) for m in read_req_list]
        self.read_resp_list = [NotMethod(m) for m in read_resp_list]
        self.send_to_fu = send_to_fu

        self.layouts = VectorBackendLayouts(self.gen_params)
        self.vrf_layout = VRFFragmentLayouts(self.gen_params)
        self.issue = Method(i = self.layouts.downloader_in)

    def elaborate(self, platform):
        m = TModule()

        regs_number = 4

        instr = Record(self.layouts.downloader_in)
        instr_valid = Signal(name = "instr_valid")
        req_counter = Signal(self.v_params.elens_in_bank_bits, name= "req_counter")
        resp_counter = Signal(self.v_params.elens_in_bank_bits, name="resp_counter")
        m.submodules.uniqness_checker = uniqness_checker = PriorityUniqnessChecker(regs_number, self.gen_params.phys_regs_bits)

        regs_fields = ["s1", "s2", "s3", "v0"]
        for i, field in enumerate(regs_fields):
            m.d.comb += uniqness_checker.inputs[i].eq(instr[field])

        for i, field in enumerate(["s1_needed", "s2_needed", "s3_needed", "v0_needed"]):
            m.d.comb += uniqness_checker.input_valids[i].eq(instr[field])

        fifos_to_vrf = [FIFO(self.vrf_layout.read_req, 2) for _ in range(regs_number)]
        fifos_to_resp_in = [FIFO(self.vrf_layout.read_resp_i, 2) for _ in range(regs_number)]
        fifos_to_resp_out = [FIFO(self.vrf_layout.read_resp_o, 2) for _ in range(regs_number)]
        m.submodules.fifos_to_vrf = ModuleConnector(*fifos_to_vrf)
        m.submodules.fifos_to_resp_in = ModuleConnector(*fifos_to_resp_in)
        m.submodules.fifos_to_resp_out = ModuleConnector(*fifos_to_resp_out)

        m.submodules.connect_req = ModuleConnector(* [ConnectTrans(fifos_to_vrf[i].read, self.read_req_list[i].method) for i in range(regs_number)])
        uniq= Signal(4, name="uniq")
        m.d.top_comb += uniq.eq(Cat(uniqness_checker.valids))
        for i in range(regs_number):
            with Transaction().body(m):
                arg = fifos_to_resp_in[i].read(m)
                fifos_to_resp_out[i].write(m, self.read_resp_list[i].method(m, arg))

        with Transaction(name = "downloader_request_trans").body(m, request = instr_valid & (req_counter != 0)):
            for i, field_name in enumerate(regs_fields):
                with m.If (uniqness_checker.valids[i] & instr[field_name + "_needed"]):
                    fifos_to_vrf[i].write(m, vrp_id = instr[field_name], addr = req_counter)
                    fifos_to_resp_in[i].write(m, vrp_id = instr[field_name])
            m.d.sync += req_counter.eq(req_counter-1)


        data_to_fu = Record(self.layouts.downloader_data_out)
        with Transaction(name = "downloader_response_trans").body(m, request = instr_valid & (resp_counter != 0)):
            for i, field in enumerate(regs_fields):
                with m.If(uniqness_checker.valids[i] & instr[field + "_needed"]):
                    m.d.comb += data_to_fu[field].eq(fifos_to_resp_out[i].read(m).data)
            m.d.sync += resp_counter.eq(resp_counter-1)
            self.send_to_fu(m, data_to_fu)
            with m.If(resp_counter == 1):
                m.d.sync += instr_valid.eq(0)


        @def_method(m, self.issue, ready = ~instr_valid)
        def _(arg):
            m.d.sync += instr.eq(arg)
            m.d.sync += instr_valid.eq(1)
            m.d.sync += req_counter.eq(arg.elems_len)
            m.d.sync += resp_counter.eq(arg.elems_len)

        return m
