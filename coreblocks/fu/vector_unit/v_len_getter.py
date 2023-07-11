from amaranth import *
from coreblocks.transactions import *
from coreblocks.transactions.lib import *
from coreblocks.utils import *
from coreblocks.params import *
from coreblocks.utils.fifo import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.fu.vector_unit.vrs import *
from coreblocks.structs_common.scoreboard import *

__all__ = ["VectorLenGetter"]

class VectorLenGetter(Elaboratable):
    def __init__(self, gen_params : GenParams, fragment_index : int):
        self.gen_params = gen_params
        self.v_params = self.gen_params.v_params
        self.fragment_index = fragment_index

        self.layouts = VectorBackendLayouts(self.gen_params)
        self.issue = Method(i = self.layouts.executor_in, o=self.layouts.len_getter_out)

        self.first_element = {eew : self.v_params.eew_to_elems_in_bank[eew] * fragment_index for eew in EEW}
        self.end_element = {eew : self.v_params.eew_to_elems_in_bank[eew] * (fragment_index + 1) for eew in EEW}


    def elaborate(self, platform):
        m = TModule()

        wskaznik = Signal(2, name="wskaznik")
        elems_len = Signal(self.v_params.eew_to_elems_in_bank_bits[EEW.w8])
        @def_method(m, self.issue)
        def _ (arg):
            with m.Switch(arg.vtype.sew):
                for sew in SEW:
                    with m.Case(sew):
                        with m.If(arg.vtype.vl > self.end_element[sew]):
                            m.d.comb += wskaznik.eq(1)
                            m.d.comb += elems_len.eq(self.v_params.eew_to_elems_in_bank[sew])
                        with m.Elif(arg.vtype.vl > self.first_element[sew]):
                            m.d.comb += wskaznik.eq(2)
                            # TODO optimisation: If the number of elements in register bank is power of two,
                            # then we can use `k`-last bits instead of doing subtraction
                            m.d.comb += elems_len.eq(arg.vtype.vl - self.first_element[sew])
                        with m.Else():
                            m.d.comb += wskaznik.eq(3)
                            m.d.comb += elems_len.eq(0)
            return {"elems_len" : elems_len}

        return m
