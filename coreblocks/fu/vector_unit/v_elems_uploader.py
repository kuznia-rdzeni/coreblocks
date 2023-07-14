from amaranth import *
from coreblocks.transactions import *
from coreblocks.transactions.lib import *
from coreblocks.utils import *
from coreblocks.params import *
from coreblocks.utils.fifo import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.fu.vector_unit.utils import *

__all__ = ["VectorElemsUploader"]

class VectorElemsUploader(Elaboratable):
    def __init__(self, gen_params : GenParams, write : Method, read_old_dst : Method, read_mask : Method, report_end : Method):
        self.gen_params = gen_params
        self.v_params = self.gen_params.v_params
        self.write = write
        self.read_old_dst = read_old_dst
        self.read_mask = read_mask
        self.report_end = report_end

        self.layouts = VectorBackendLayouts(self.gen_params)
        self.vrf_layout = VRFFragmentLayouts(self.gen_params)
        self.issue = Method(i = self.layouts.uploader_result_in)
        self.init = Method(i = self.layouts.uploader_init_in)

    def elaborate(self, platform):
        m = TModule()

        vrp_id_saved = Signal(self.v_params.vrp_count_bits)
        write_counter = Signal(self.v_params.elens_in_bank_bits, name= "write_counter")
        uploader_ready = Signal()

        @def_method(m, self.issue, ready = write_counter != 0)
        def _(dst_val):
            old_dst_val = self.read_old_dst(m)
            mask = self.read_mask(m).mask

            mask_expanded = Signal(self.v_params.elen)
            m.d.top_comb += mask_expanded.eq(expand_mask(self.v_params, mask))
            addr = Signal().like(write_counter)
            m.d.top_comb += addr.eq(write_counter - 1)

            #this implements mask undisturbed policy
            self.write(m, vrp_id = vrp_id_saved , addr = addr, valid_mask = 2 ** self.v_params.bytes_in_elen - 1, data = (mask_expanded & dst_val) | (~mask_expanded & old_dst_val))
            m.d.sync += write_counter.eq(addr)

        end_reporter = Transaction()
        self.issue.schedule_before(end_reporter)
        with end_reporter.body(m, request = write_counter==1 & self.issue.run):
            self.report_end(m)
        
        @def_method(m, self.init)
        def _(vrp_id, ma, elems_len):
            m.d.sync += write_counter.eq(elems_len)
            m.d.sync += vrp_id_saved.eq(vrp_id)

        return m
