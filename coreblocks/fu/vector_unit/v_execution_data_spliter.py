from amaranth import *
from coreblocks.transactions import *
from coreblocks.utils import *
from coreblocks.params import *
from coreblocks.fu.vector_unit.v_layouts import *

__all__ = ["VectorExecutionDataSplitter"]


class VectorExecutionDataSplitter(Elaboratable):
    """
    A support module used to convert the layout of the downloaded data,
    fill it with the additional fields that are constant for the
    duration of the whole instruction, and send it to the appropriate
    modules in the `VectorExecutor`. Each input record generates
    one record for:
    - `VectorAlu`
    - `VectorMaskExtractor`
    - old destination value fifo

    This module also prepars input data for the vector FU
    if the first operand is a scalar or an immediate.

    Attributes
    ----------
    issue : Method
        Used to pass the newly downloaded entry from the vector register.
    init : Method
        The method called to pass data that is constant for the duration
        of the entire instruction.
    """

    def __init__(self, gen_params: GenParams, put_fu: Method, put_old_dst: Method, put_mask: Method):
        """
        Parameters
        ----------
        gen_params : GenParams
            Core configuration.
        put_fu : Method
            The method called to pass arguments to `VectorAlu`.
        put_old_dst : Method
            Called to pass the old register destination value.
        put_mask : Method
            Passes data to be processed by the `VectorMaskExtractor`.
        """
        self.gen_params = gen_params
        self.v_params = self.gen_params.v_params
        self.put_fu = put_fu
        self.put_old_dst = put_old_dst
        self.put_mask = put_mask

        self.layouts = VectorBackendLayouts(self.gen_params)
        self.alu_layouts = VectorAluLayouts(self.gen_params)

        self.issue = Method(i=self.layouts.data_splitter_in)
        self.init = Method(i=self.layouts.data_splitter_init_in)

    def elaborate(self, platform):
        m = TModule()

        vtype_saved = Record(VectorCommonLayouts(self.gen_params).vtype)
        exec_fn_saved = Record(self.gen_params.get(CommonLayouts).exec_fn)
        s1_val_saved = Signal(self.gen_params.isa.xlen)

        @def_method(m, self.init)
        def _(vtype, exec_fn, s1_val):
            m.d.sync += vtype_saved.eq(vtype)
            m.d.sync += exec_fn_saved.eq(exec_fn)
            m.d.sync += s1_val_saved.eq(s1_val)

        @def_method(m, self.issue)
        def _(s1, s2, s3, v0, elen_index, last_mask):
            fu_data = Record(self.alu_layouts.alu_in)
            imm_or_scalar = Signal()
            m.d.top_comb += imm_or_scalar.eq(
                (exec_fn_saved.funct3 == Funct3.OPIVI) | (exec_fn_saved.funct3 == Funct3.OPIVX)
            )
            m.d.top_comb += fu_data.s1.eq(Mux(imm_or_scalar, s1_val_saved, s1))
            m.d.top_comb += fu_data.s2.eq(s2)
            m.d.top_comb += fu_data.eew.eq(vtype_saved.sew)
            m.d.top_comb += fu_data.exec_fn.eq(exec_fn_saved)
            self.put_fu(m, fu_data)

            mask_data = Record(self.layouts.mask_extractor_in)
            m.d.top_comb += mask_data.elen_index.eq(elen_index)
            m.d.top_comb += mask_data.v0.eq(v0)
            m.d.top_comb += mask_data.eew.eq(vtype_saved.sew)
            m.d.top_comb += mask_data.vm.eq(exec_fn_saved.funct7[0])
            m.d.top_comb += mask_data.last_mask.eq(last_mask)
            self.put_mask(m, mask_data)

            old_dst_data = Record(self.layouts.uploader_old_dst_in)
            m.d.top_comb += old_dst_data.old_dst_val.eq(s3)
            self.put_old_dst(m, old_dst_data)

        return m
