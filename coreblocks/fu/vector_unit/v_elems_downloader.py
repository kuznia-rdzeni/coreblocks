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
    def __init__(self, gen_params : GenParams, read_req_list : list[Method], read_resp_list : list[Method]):
        self.gen_params = gen_params
        self.v_params = self.gen_params.v_params
        self.read_req_list = read_req_list
        self.read_resp_list = read_resp_list

        self.layouts = VectorBackendLayouts(self.gen_params)
        self.issue = Method(i = self.layouts.executor_in)

    def elaborate(self, platform):
        m = TModule()

        #TODO optimise when requesting data from the same address from the same register
        # now there are sent two requests, which cause a conflict, so they handling take two cycles

        instr = Record(self.layouts.downloader_in)
        instr_valid = Signal()
        counter = Signal(self.v_params.eew_to_elems_in_bank_bits[EEW.w8])
        m.submodules.uniqness_checker = uniqness_checker = PriorityUniqnessChecker(4, self.gen_params.phys_regs_bits)

        for i, field in enumerate(["s1", "s2", "s3", "v0"]):
            m.d.comb += uniqness_checker.inputs[i].eq(instr[field])

        for i, field in enumerate(["s1_needed", "s2_needed", "s3_needed", "v0_needed"]):
            m.d.comb += uniqness_checker.input_valids[i].eq(instr[field])

        with Transaction(name = "downloader_request_trans").body(m, request = instr_valid & (counter != 0)):
            for i in range(4):
                with condition(m, 

        @def_method(m, self.issue, ready = ~instr_valid)
        def _(arg):
            m.d.sync += instr.eq(arg)
            m.d.sync += instr_valid.eq(1)
            m.d.sync += counter.eq(instr.elems_len)
