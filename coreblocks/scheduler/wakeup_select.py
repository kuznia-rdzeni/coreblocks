from typing import Optional

from amaranth import *

from coreblocks.params import GenParams
from coreblocks.interface.layouts import FuncUnitLayouts, RSLayouts
from coreblocks.telemetry import FuIssue
from transactron.evlog import EventSource
from transactron.utils import PriorityEncoder, assign, AssignType
from transactron.core import *

__all__ = ["WakeupSelect"]


evlog = EventSource("backend.wakeup_select")


class WakeupSelect(Elaboratable):
    """
    Simple Wakeup Select unit.
    Works by firstly getting readiness vector from the method `get_ready` (it is a binary vector,
    where 1 on i-th position means i-th row is ready to be taken and 0 means it is not). In next
    step if any row is ready to be taken it calls `take_row` with i (position of last ready row)
    as an argument in order to get its value and then calls method `issue` with i-th row as
    argument. It is prepared to work with RS and functional unit interfaces.

    Attributes
    ----------
    get_ready : Method, required
        Method which is invoked to get the vector of readiness. It uses `RSLayouts.get_ready_list_out`.
    take_row : Method, required
        Method which is invoked to get a single ready row. It uses `RSLayouts.take_out`.
    issue : Method, required
        Method which is invoked to a push row down the pipeline. It uses `FuncUnitLayouts.issue`.
    """

    get_ready: Required[Method]
    take_row: Required[Method]
    issue: Required[Method]

    def __init__(self, *, gen_params: GenParams, rs_entries: int, fu_kind: Optional[str] = None):
        """
        Parameters
        ----------
        gen_params : GenParams
            Instance of GenParams with parameters describing the core.
        rs_entries : int
            Number of entries of the RS connected to this instance of WakeupSelect.
        fu_kind : str, optional
            Name of the functional unit fed by this instance, reported in the
            event log on every issue.
        """
        self.gen_params = gen_params
        self.fu_kind = fu_kind
        rs_layouts = gen_params.get(RSLayouts, rs_entries=rs_entries)
        self.get_ready = Method(o=rs_layouts.get_ready_list_out)  # assumption: ready only if nonzero result
        self.take_row = Method(i=rs_layouts.take_in, o=rs_layouts.take_out)
        self.issue = Method(i=gen_params.get(FuncUnitLayouts).issue)

    def elaborate(self, platform):
        m = TModule()

        with Transaction().body(m):
            ready = self.get_ready(m)
            ready_width = len(ready.ready_list)
            m.submodules.prio_encoder = prio_encoder = PriorityEncoder(ready_width)
            m.d.av_comb += prio_encoder.i.eq(ready.ready_list)
            row = self.take_row(m, prio_encoder.o)
            issue_rec = Signal(self.gen_params.get(FuncUnitLayouts).issue)
            m.d.av_comb += assign(issue_rec, row, fields=AssignType.ALL)
            self.issue(m, issue_rec)

            if self.fu_kind is not None:
                evlog.emit(m, FuIssue.hw(rob_id=issue_rec.rob_id, unit=self.fu_kind))

        return m
