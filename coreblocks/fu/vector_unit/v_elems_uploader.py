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
    """Module responsible for sending data back to the vector register.

    Once initiated, this module will get the old value stored in the destination
    register downloaded by the vector downloader, the mask in the byte format
    and the results of the vector FU. It combines this data and sends
    results to the vector destination register using the mask undisturbed
    policy.

    When all elements requested to be seny on initialisation have been
    sent, the `VectorElemsUploader` reports this fact to the
    `VectorExecutionEnder`.

    Attributes
    ----------
    issue : Method
        The method to call when new results from the vector FU are
        ready to be sent to the register.
    init : Method
        Called to pass the instruction configuration at the start of
        execution of the new instruction.
    """

    def __init__(
        self, gen_params: GenParams, write: Method, read_old_dst: Method, read_mask: Method, report_end: Method
    ):
        """
        Parameters
        ----------
        gen_params : GenParams
            Core configuration.
        write : Method
            The method called to write a new entry into the vector register.
        read_old_dst : Method
            Called to get the old register destination value of the element
            currently being processed.
        read_mask : Method
            Get the byte mask to be applied to the results calculated
            by the vector FU before sending them to the register. Invalid
            bytes are substituted with the old register destination value.
        report_end : Method
            Used to inform about the end of instruction execution.
        """
        self.gen_params = gen_params
        self.v_params = self.gen_params.v_params
        self.write = write
        self.read_old_dst = read_old_dst
        self.read_mask = read_mask
        self.report_end = report_end

        self.layouts = VectorBackendLayouts(self.gen_params)
        self.vrf_layout = VRFFragmentLayouts(self.gen_params)
        self.issue = Method(i=self.layouts.uploader_result_in)
        self.init = Method(i=self.layouts.uploader_init_in)

    def elaborate(self, platform):
        m = TModule()

        vrp_id_saved = Signal(self.v_params.vrp_count_bits)
        write_counter = Signal(self.v_params.elens_in_bank_bits, name="write_counter")
        end_to_report = Signal()

        @def_method(m, self.issue, ready=write_counter != 0)
        def _(dst_val):
            old_dst_val = self.read_old_dst(m)
            mask = self.read_mask(m).mask

            mask_expanded = Signal(self.v_params.elen)
            m.d.top_comb += mask_expanded.eq(expand_mask(self.v_params, mask))
            addr = Signal(range(self.v_params.elens_in_bank))
            m.d.top_comb += addr.eq(write_counter - 1)

            # this implements mask undisturbed policy
            self.write(
                m,
                vrp_id=vrp_id_saved,
                addr=addr,
                valid_mask=2**self.v_params.bytes_in_elen - 1,
                data=(mask_expanded & dst_val) | (~mask_expanded & old_dst_val),
            )
            m.d.sync += write_counter.eq(addr)

        end_reporter = Transaction()
        self.issue.schedule_before(end_reporter)
        with end_reporter.body(
            m, request=((write_counter == 1) & self.issue.run) | (end_to_report & (write_counter == 0))
        ):
            self.report_end(m)
            m.d.sync += end_to_report.eq(0)

        end_reporter.schedule_before(self.init)

        @def_method(m, self.init, ready=end_reporter.grant | ~end_to_report)
        def _(vrp_id, ma, elens_len):
            m.d.sync += write_counter.eq(elens_len)
            m.d.sync += vrp_id_saved.eq(vrp_id)
            m.d.sync += end_to_report.eq(1)

        return m
