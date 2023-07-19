from amaranth import *
from coreblocks.transactions import *
from coreblocks.params import *
from coreblocks.utils.utils import PriorityUniqnessChecker

__all__ = ["Scoreboard"]


class Scoreboard(Elaboratable):
    """
    This module implements a scoreboard. A simple structure that allows
    to store a dirty bit for each of the indicies.

    Attributes
    ----------
    get_dirty_list : list[Method]
        Methods to get the dirty bit for the given index id.
        Layout: ScoreboardLayouts.get_dirty_*
    set_dirty_list : list[Method]
        Methods to set the dirty bit for the given index id. If more than
        one method try to write to the same index, the method
        with the lowest index in list has a priority.
        Layout: ScoreboardLayouts.set_dirty_in
    """

    def __init__(self, entries_number: int, superscalarity: int = 1, *, data_forward=False):
        self.entries_number = entries_number
        self.superscalarity = superscalarity
        self.data_forward = data_forward

        self.layouts = ScoreboardLayouts(self.entries_number)
        self.get_dirty_list = [
            Method(i=self.layouts.get_dirty_in, o=self.layouts.get_dirty_out, name=f"get{i}")
            for i in range(self.superscalarity)
        ]
        self.set_dirty_list = [Method(i=self.layouts.set_dirty_in, name=f"set{i}") for i in range(self.superscalarity)]

        for i in range(1, self.superscalarity):
            self.set_dirty_list[i - 1].schedule_before(self.set_dirty_list[i])

    def elaborate(self, platform) -> TModule:
        m = TModule()

        data = Signal(self.entries_number, name="data")
        m.submodules.checker = checker = PriorityUniqnessChecker(
            self.superscalarity, len(Record(self.layouts.set_dirty_in).id), non_valid_ok=True
        )

        if self.data_forward:
            data_forward = Signal(self.entries_number, name="data_forward")
            data_forward_valid = Signal(self.entries_number, name="data_forward_valid")

        @loop_def_method(m, self.set_dirty_list, ready_list=checker.valids)
        def _(i, id, dirty):
            m.d.top_comb += checker.inputs[i].eq(id)
            m.d.top_comb += checker.input_valids[i].eq(self.set_dirty_list[i].run)
            m.d.sync += data.bit_select(id, 1).eq(dirty)
            if self.data_forward:
                m.d.comb += data_forward.bit_select(id, 1).eq(dirty)
                m.d.comb += data_forward_valid.bit_select(id, 1).eq(1)

        @loop_def_method(m, self.get_dirty_list)
        def _(_, id):
            output = Record(self.layouts.get_dirty_out)
            if self.data_forward:
                m.d.top_comb += output.dirty.eq(
                    Mux(data_forward_valid.bit_select(id, 1), data_forward.bit_select(id, 1), data.bit_select(id, 1))
                )
            else:
                m.d.top_comb += output.dirty.eq(data.bit_select(id, 1))
            return output

        return m
