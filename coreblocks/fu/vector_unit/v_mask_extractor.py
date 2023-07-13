from amaranth import *
from coreblocks.transactions import *
from coreblocks.transactions.lib import *
from coreblocks.utils import *
from coreblocks.params import *
from coreblocks.utils.fifo import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.fu.vector_unit.utils import *

__all__ = ["VectorMaskExtractor"]

def elem_mask_to_byte_mask(m : TModule, v_params : VectorParameters, elem_mask : Value, eew : Value):
    result = Signal(v_params.bytes_in_elen)
    with m.Switch(eew):
        for eew_iter in EEW:
            with m.Case(eew_iter):
                m.d.av_comb += result.eq(Cat([Repl(bit, 2**int(eew_iter)) for bit in elem_mask[:v_params.elen//eew_to_bits(eew_iter)]]))
    return result
                

class VectorMaskExtractor(Elaboratable):
    def __init__(self, gen_params : GenParams, put_mask : Method):
        self.gen_params = gen_params
        self.v_params = self.gen_params.v_params
        self.put_mask = put_mask

        self.layouts = VectorBackendLayouts(self.gen_params)
        self.issue = Method(i = self.layouts.mask_extractor_in)

    def elaborate(self, platform):
        m = TModule()

        # elen_index - index from which standard operands have been fetched
        @def_method(m, self.issue)
        def _(v0 : Value, elen_index : Value, eew : Value, vm : Value):
            number_of_described_elements=Signal(6)
            m.d.comb += number_of_described_elements.eq( 8<<eew)
            rest = Signal(32, name = "rest")
            m.d.comb += rest.eq(elen_index & (number_of_described_elements - 1))
            start = Signal(log2_int(self.v_params.elen))
            m.d.comb += start.eq((rest << bits_to_eew(self.v_params.elen) ) >> eew)
            mask = Signal(self.v_params.bytes_in_elen)
            with m.Switch(eew):
                for eew_iter in EEW:
                    if eew_to_bits(eew_iter)<=self.v_params.elen:
                        with m.Case(eew_iter):
                            m.d.comb += mask.eq(v0.bit_select(start, self.v_params.elen // eew_to_bits(eew_iter)))
            out_mask = Signal(self.v_params.bytes_in_elen)
            with m.If(vm==0):
                m.d.comb += out_mask.eq(elem_mask_to_byte_mask(m, self.v_params, mask, eew))
            with m.Else():
                m.d.comb += out_mask.eq(2**self.v_params.bytes_in_elen-1)
            self.put_mask(m, mask = out_mask)
        return m
