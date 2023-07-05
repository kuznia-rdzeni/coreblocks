from amaranth import *
from coreblocks.transactions import *
from coreblocks.transactions.lib import *
from coreblocks.params import *
from coreblocks.fu.vector_unit.utils import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.utils.fifo import BasicFifo
from coreblocks.utils.utils import PriorityUniqnessChecker

__all__ = ["Scoreboard"]

class Scoreboard(Elaboratable):
    def __init__(self, entries_number : int, superscalarity : int = 1):
        self.entries_number = entries_number
        self.superscalarity = superscalarity
        
        self.layouts = ScoreboardLayouts(self.entries_number)
        self.get_dirty_list = [Method(i=self.layouts.get_dirty_in, o=self.layouts.get_dirty_out) for _ in range(self.superscalarity)]
        self.set_dirty_list = [Method(i=self.layouts.set_dirty_in) for _ in range(self.superscalarity)]

        for i in range(1, self.superscalarity):
            self.set_dirty_list[i-1].schedule_before(self.set_dirty_list[i])

    def elaborate(self, platform) -> TModule:
        m = TModule()

        data = Signal(self.entries_number)
        m.submodules.checker = checker = PriorityUniqnessChecker(self.superscalarity, len(Record(self.layouts.set_dirty_in).id))

        @loop_def_method(m, self.get_dirty_list)
        def _(_, id):
            return {"dirty" : data.bit_select(id, 1)}

        @loop_def_method(m, self.set_dirty_list, ready_list = checker.valids)
        def _(i, id, dirty):
            m.d.top_comb += checker.inputs[i].eq(id)
            m.d.top_comb += checker.input_valids[i].eq(self.set_dirty_list[i].run)
            m.d.sync += data.bit_select(id, 1).eq(dirty)

        return m
