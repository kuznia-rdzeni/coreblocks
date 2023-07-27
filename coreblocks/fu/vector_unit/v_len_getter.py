from amaranth import *
from amaranth.lib.coding import Decoder
from coreblocks.transactions import *
from coreblocks.utils import *
from coreblocks.params import *
from coreblocks.fu.vector_unit.v_layouts import *

__all__ = ["VectorLenGetter"]


class VectorLenGetter(Elaboratable):
    """Calculate number of entries to download from vector registry

    This module takes a `vl` set in vector status and a register bank id
    and calculates based on that the number of entries (each ELEN width) rounded
    up to download from registers in that bank.

    In addition, it produces a mask in the elems format, indicating which elements
    from the last entry are valid.

    Attributes
    ----------
    issue : Method
        Used to request a calculation of the elens length.
    """

    def __init__(self, gen_params: GenParams, fragment_index: int):
        """
        Parameters
        ----------
        gen_params : GenParams
            Core configuration.
        fragment_index : int
            Index of the register bank for which calculations are to be performed.
        """
        self.gen_params = gen_params
        self.v_params = self.gen_params.v_params
        self.fragment_index = fragment_index

        self.layouts = VectorBackendLayouts(self.gen_params)
        self.issue = Method(i=self.layouts.executor_in, o=self.layouts.len_getter_out)

        self.first_element = {eew: self.v_params.eew_to_elems_in_bank[eew] * fragment_index for eew in EEW}
        self.end_element = {eew: self.v_params.eew_to_elems_in_bank[eew] * (fragment_index + 1) for eew in EEW}

    def elaborate(self, platform):
        m = TModule()

        m.submodules.binary_to_onehot = binary_to_onehot = Decoder(self.v_params.bytes_in_elen + 1)

        elens_len = Signal(self.v_params.elens_in_bank_bits)
        last_mask = Signal(self.v_params.bytes_in_elen)

        #TODO add support for tail undisturbed policy
        @def_method(m, self.issue)
        def _(arg):
            with m.Switch(arg.vtype.sew):
                for sew in SEW:
                    if eew_to_bits(sew) <= self.v_params.elen:
                        with m.Case(sew):
                            with m.If(arg.vtype.vl > self.end_element[sew]):
                                m.d.comb += elens_len.eq(self.v_params.elens_in_bank)
                                m.d.comb += last_mask.eq(2 ** (self.v_params.elen // eew_to_bits(sew)) - 1)
                            with m.Elif(arg.vtype.vl > self.first_element[sew]):
                                # TODO optimisation: If the number of elements in register bank is power of two,
                                # then we can use `k`-last bits instead of doing subtraction
                                elems_count = Signal().like(arg.vtype.vl)
                                m.d.top_comb += elems_count.eq(arg.vtype.vl - self.first_element[sew])
                                elem_count_modulo = Signal(bits_for(self.v_params.bytes_in_elen))
                                m.d.top_comb += elem_count_modulo.eq(
                                    elems_count & (2 ** (bits_to_eew(self.v_params.elen) - sew) - 1)
                                )
                                m.d.comb += elens_len.eq(
                                    (elems_count >> (bits_to_eew(self.v_params.elen) - sew)) + elem_count_modulo.any()
                                )
                                m.d.comb += binary_to_onehot.i.eq(elem_count_modulo)
                                m.d.comb += last_mask.eq(
                                    Mux(
                                        elem_count_modulo.any(),
                                        binary_to_onehot.o - 1,
                                        2 ** (self.v_params.elen // eew_to_bits(sew)) - 1,
                                    )
                                )
                            with m.Else():
                                m.d.comb += elens_len.eq(0)
                                m.d.comb += last_mask.eq(0)
            # last_mask is in elems mask format
            return {"elens_len": elens_len, "last_mask": last_mask}

        return m
