from amaranth import *
from coreblocks.transactions import *
from coreblocks.params import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.fu.vector_unit.utils import *

__all__ = ["VectorMaskExtractor"]


def elem_mask_to_byte_mask(m: TModule, v_params: VectorParameters, elem_mask: Value, eew: Value):
    """ Generate a circuit to convert the mask from the elem format to the byte format.

    The elem format always has valid first `k` bits where `k = ELEN/EEW` and each
    bit describes whether an element is valid or not. The byte format has always `ELEN//8`
    bits and each bit represents wheter a byte is valid or not.

    Parameters
    ----------
    m : TModule
        Module to connect the circuit to.
    v_params : VectorParameters
        Vector unit configuration.
    elem_mask : Value
        Mask in elem format to be converted.
    eew : Value(EEW)
        The EEW for which the `elem_mask` was generated.

    Returns
    -------
    Mask in byte format.
    """
    result = Signal(v_params.bytes_in_elen)
    with m.Switch(eew):
        for eew_iter in EEW:
            with m.Case(eew_iter):
                m.d.av_comb += result.eq(
                    Cat([Repl(bit, 2 ** int(eew_iter)) for bit in elem_mask[: v_params.elen // eew_to_bits(eew_iter)]])
                )
    return result


class VectorMaskExtractor(Elaboratable):
    """ Module used to extract mask from the vector register entry

    The vector mask is always downloaded from `v0`, and the `VectorElemsDownloader`
    always downloads `ELEN` bits. From that only `ELEN/EEW` bits are
    valid. This module extracts these bits based on the index from which
    the standard operands were fetched.

    Mask is returned in the byte format.

    Attributes
    ----------
    issue : Method
        Request extracting of the mask.
    """
    def __init__(self, gen_params: GenParams, put_mask: Method):
        """
        Parameters
        ----------
        gen_params : GenParams
            Core configuration.
        put_mask : Method
            The method to insert the calculated mask.
        """
        self.gen_params = gen_params
        self.v_params = self.gen_params.v_params
        self.put_mask = put_mask

        self.layouts = VectorBackendLayouts(self.gen_params)
        self.issue = Method(i=self.layouts.mask_extractor_in)

    def elaborate(self, platform):
        m = TModule()

        # elen_index - index from which standard operands have been fetched
        @def_method(m, self.issue)
        def _(v0: Value, elen_index: Value, eew: Value, vm: Value, last_mask: Value):
            number_of_described_elements = 8 << eew
            rest = elen_index & (number_of_described_elements - 1)
            start = Signal(log2_int(self.v_params.elen))
            m.d.comb += start.eq((rest << bits_to_eew(self.v_params.elen)) >> eew)
            mask = Signal(self.v_params.bytes_in_elen)
            with m.Switch(eew):
                for eew_iter in EEW:
                    if eew_to_bits(eew_iter) <= self.v_params.elen:
                        with m.Case(eew_iter):
                            m.d.comb += mask.eq(v0.bit_select(start, self.v_params.elen // eew_to_bits(eew_iter)))
            out_mask = Signal(self.v_params.bytes_in_elen)
            with m.If(vm == 0):
                m.d.comb += out_mask.eq(mask)
            with m.Else():
                m.d.comb += out_mask.eq(2**self.v_params.bytes_in_elen - 1)
            self.put_mask(m, mask=elem_mask_to_byte_mask(m, self.v_params, out_mask & last_mask, eew))

        return m
