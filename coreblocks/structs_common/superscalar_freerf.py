from typing import Optional
from amaranth import *
from coreblocks.transactions import *
from coreblocks.transactions.lib import *
from coreblocks.utils import *
from coreblocks.params import *
from coreblocks.fu.vector_unit.utils import *
from coreblocks.fu.vector_unit.v_layouts import *


class SuperscalarFreeRF(Elaboratable):
    def __init__(self, entries_count : int, outputs_count : int):
        self.entries_count = entries_count
        self.outputs_count = outputs_count

        self.layouts = SuperscalarFreeRFLayouts(self.entries_count, self.outputs_count)
        self.allocate = Method(i=self.layouts.allocate_in, o=self.layouts.allocate_out)
        self.deallocates = [Method(i=self.layouts.deallocate_in) for _ in range(self.outputs_count)]

    def elaborate(self, platform) -> TModule:
        m = TModule()

        self.used = Signal(self.entries_count)

        m.submodules.priority_encoder = encoder = MultiPriorityEncoder(self.entries_count, self.outputs_count)
        m.d.top_comb += encoder.input.eq(self.used)

        free_count = Signal(log2_int(self.entries_count))
        m.d.top_comb += free_count.eq(count_trailing_zeros(~Cat(encoder.valids)))

        regs = [Signal.like(encoder.outputs[j]) for j in range(self.outputs_count)]

        # ONE CALLER!
        @def_method(m, self.allocate)
        def _(reg_count):
            with condition(m, nonblocking = False) as branch:
                with branch(reg_count <= free_count):
                    mask = (2 << reg_count) - 1
                    for j in range(self.outputs_count):
                        used_bit = Signal()
                        m.d.comb += used_bit.eq(self.used.bit_select(encoder.outputs[j], 1))
                        m.d.sync += self.used.bit_select(encoder.outputs[j], 1).eq(used_bit & (~mask[j]))
                        m.d.comb += regs[j].eq(encoder.outputs[j])
            return {f"reg{i}":regs[i] for i in range(self.outputs_count)}


        @loop_def_method(m, self.deallocates)
        def _(_, reg):
            m.d.sync += self.used.bit_select(reg, 1).eq(1)


        return m
