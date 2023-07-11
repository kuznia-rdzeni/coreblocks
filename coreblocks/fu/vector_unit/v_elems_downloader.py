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
        self.read_req_list = read_req_list
        self.read_resp_list = read_resp_list
        self.send_to_fu = send_to_fu

        self.layouts = VectorBackendLayouts(self.gen_params)
        self.issue = Method(i = self.layouts.executor_in)

    def elaborate(self, platform):
        m = TModule()

        instr = Record(self.layouts.downloader_in)
        instr_valid = Signal()
        req_counter = Signal(self.v_params.eew_to_elems_in_bank_bits[EEW.w8])
        resp_counter = Signal(self.v_params.eew_to_elems_in_bank_bits[EEW.w8])
        m.submodules.uniqness_checker = uniqness_checker = PriorityUniqnessChecker(4, self.gen_params.phys_regs_bits)

        regs_fields = ["s1", "s2", "s3", "v0"]
        for i, field in enumerate(regs_fields):
            m.d.comb += uniqness_checker.inputs[i].eq(instr[field])

        for i, field in enumerate(["s1_needed", "s2_needed", "s3_needed", "v0_needed"]):
            m.d.comb += uniqness_checker.input_valids[i].eq(instr[field])

        with Transaction(name = "downloader_request_trans").body(m, request = instr_valid & (req_counter != 0)):
            for i, field in enumerate(regs_fields):
                with connected_conditions(m, nonblocking = False) as cond:
                    with cond() as branch:
                        with branch(uniqness_checker.valids[i]):
                            self.read_req_list[i](m, instr[field])
            m.d.sync += req_counter.eq(req_counter-1)

        data_to_fu = Record(self.layouts.downloader_data_out)
        with Transaction(name = "downloader_response_trans").body(m, request = instr_valid & (resp_counter != 0)):
            for i, field in enumerate(regs_fields):
                with connected_conditions(m, nonblocking = False) as cond:
                    with cond() as branch:
                        with branch(uniqness_checker.valids[i]):
                            m.d.top_comb += data_to_fu[field].eq(self.read_resp_list[i](m).data)
            m.d.sync += resp_counter.eq(resp_counter-1)
            self.send_to_fu(m, data_to_fu)
            with m.If(resp_counter == 1):
                m.d.sync += instr_valid.eq(0)


        @def_method(m, self.issue, ready = ~instr_valid)
        def _(arg):
            m.d.sync += instr.eq(arg)
            m.d.sync += instr_valid.eq(1)
            m.d.sync += req_counter.eq(instr.elems_len)
            m.d.sync += resp_counter.eq(instr.elems_len)
