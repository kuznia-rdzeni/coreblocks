from amaranth import *
from coreblocks.params.dependencies import DependencyManager
from coreblocks.params.genparams import GenParams

from coreblocks.params.isa import BitEnum
from coreblocks.params.layouts import ExceptionRegisterLayouts
from coreblocks.params.keys import ExceptionReportKey
from coreblocks.transactions.core import Priority, TModule, def_method, Method


class Cause(BitEnum, width=4):
    INSTRUCTION_ADDRESS_MISALIGNED = 0
    INSTRUCTION_ACCESS_FAULT = 1
    ILLEGAL_INSTRUCTION = 2
    BREAKPOINT = 3
    LOAD_ADDRESS_MISALIGNED = 4
    LOAD_ACCESS_FAULT = 5
    STORE_ADDRESS_MISALIGNED = 6
    STORE_ACCESS_FAULT = 7
    ENVIRONMENT_CALL_FROM_U = 8
    ENVIRONMENT_CALL_FROM_S = 9
    ENVIRONMENT_CALL_FROM_M = 11
    INSTRUCTION_PAGE_FAULT = 12
    LOAD_PAGE_FAULT = 13
    STORE_PAGE_FAULT = 15


def should_update_prioriy(m: TModule, current_cause: Value, new_cause: Value) -> Value:
    # Comparing all priorities would be expensive, this function only checks conditions that could happen in hardware
    _update = Signal()

    # All breakpoint kinds have the highest priority in conflicting cases
    with m.If(new_cause == Cause.BREAKPOINT):
        m.d.comb += _update.eq(1)

    with m.If((new_cause == Cause.INSTRUCTION_PAGE_FAULT) | (new_cause == Cause.INSTRUCTION_ACCESS_FAULT)):
        m.d.comb += _update.eq(1)

    with m.If(
        (new_cause == Cause.LOAD_ADDRESS_MISALIGNED)
        & ((current_cause == Cause.LOAD_ACCESS_FAULT) | (current_cause == Cause.LOAD_PAGE_FAULT))
    ):
        m.d.comb += _update.eq(1)

    with m.If(
        (new_cause == Cause.STORE_ADDRESS_MISALIGNED)
        & ((current_cause == Cause.STORE_ACCESS_FAULT) | (current_cause == Cause.STORE_PAGE_FAULT))
    ):
        m.d.comb += _update.eq(1)

    return _update


class ExceptionCauseRegister(Elaboratable):
    def __init__(self, gp: GenParams, rob_get_indices: Method):
        self.gp = gp

        self.cause = Signal(Cause)
        self.rob_id = Signal(gp.rob_entries_bits)
        self.valid = Signal()

        self.report = Method(i=gp.get(ExceptionRegisterLayouts).report)
        dm = gp.get(DependencyManager)
        dm.add_dependency(ExceptionReportKey(), self.report)

        self.clear = Method()

        self.clear.add_conflict(self.report, Priority.LEFT)

        self.rob_get_indices = rob_get_indices

    def elaborate(self, platform):
        m = TModule()

        @def_method(m, self.report)
        def _(cause, rob_id):
            should_write = Signal()

            with m.If(self.valid & (self.rob_id == rob_id)):
                m.d.comb += should_write.eq(should_update_prioriy(m, current_cause=self.cause, new_cause=cause))
            with m.Elif(self.valid):
                rob_start_idx = self.rob_get_indices(m).start
                m.d.comb += should_write.eq((rob_id - rob_start_idx) < (self.rob_id - rob_start_idx))
            with m.Else():
                m.d.comb += should_write.eq(1)

            with m.If(should_write):
                m.d.sync += self.rob_id.eq(rob_id)
                m.d.sync += self.cause.eq(cause)

            m.d.sync += self.valid.eq(1)

        @def_method(m, self.clear)
        def _():
            m.d.sync += self.valid.eq(0)

        return m
