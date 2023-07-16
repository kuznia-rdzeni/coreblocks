from amaranth import *
from amaranth.utils import log2_int
from coreblocks.transactions import *
from coreblocks.transactions.lib import *
from coreblocks.utils import *
from coreblocks.params import *

__all__ = ["SuperscalarFreeRF"]


class SuperscalarFreeRF(Elaboratable):
    """Superscalar structure for holding free registers

    This module is intended to hold information about physical
    registers that aren't currently in use, and to provide superscalar
    selection of free registers ids.

    Attributes
    ----------
    allocate : Method(one_caller=True)
        Method to get `reg_count` free registers. If the requested
        registers number of registers is greater than the actual number of free registers
        no registers are being allocated and the method is inactive.
    deallocates : list[Method]
        List with `outputs_count` methods. Each of them allows to deallocate
        one register in one cycle.
    """

    def __init__(self, entries_count: int, outputs_count: int):
        """
        Parameters
        ----------
        entries_count : int
            The total number of registers that should be available in the core.
        outputs_count : int
            Number of the deallocate methods that should be created to allow for
            superscalar freeing of registers.
        """
        self.entries_count = entries_count
        self.outputs_count = outputs_count

        self.layouts = SuperscalarFreeRFLayouts(self.entries_count, self.outputs_count)
        self.allocate = Method(i=self.layouts.allocate_in, o=self.layouts.allocate_out)
        self.deallocates = [Method(i=self.layouts.deallocate_in) for _ in range(self.outputs_count)]

    def elaborate(self, platform) -> TModule:
        m = TModule()

        self.not_used = Signal(self.entries_count, reset=2**self.entries_count - 1)

        m.submodules.priority_encoder = encoder = MultiPriorityEncoder(self.entries_count, self.outputs_count)
        m.d.top_comb += encoder.input.eq(self.not_used)

        free_count = Signal(log2_int(self.entries_count, False), name="free_count")
        m.d.top_comb += free_count.eq(count_trailing_zeros(~Cat(encoder.valids)))

        regs = [Signal.like(encoder.outputs[j]) for j in range(self.outputs_count)]

        # one caller!
        @def_method(m, self.allocate)
        def _(reg_count):
            with condition(m, nonblocking=False) as branch:
                branch_cond = Signal()
                m.d.top_comb += branch_cond.eq((reg_count <= free_count) & (reg_count > 0))
                with branch(branch_cond):
                    mask = (1 << reg_count) - 1
                    for j in range(self.outputs_count):
                        used_bit = Signal()
                        m.d.comb += used_bit.eq(self.not_used.bit_select(encoder.outputs[j], 1))
                        m.d.sync += self.not_used.bit_select(encoder.outputs[j], 1).eq(used_bit & (~mask[j]))
                        m.d.comb += regs[j].eq(encoder.outputs[j])
            return {f"reg{i}": regs[i] for i in range(self.outputs_count)}

        @loop_def_method(m, self.deallocates)
        def _(_, reg):
            m.d.sync += self.not_used.bit_select(reg, 1).eq(1)

        return m
