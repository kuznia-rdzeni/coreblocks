from amaranth import *
from coreblocks.params.genparams import GenParams

from coreblocks.params.isa import BitEnum
from coreblocks.params.layouts import ExceptionRegisterLayouts
from coreblocks.transactions.core import Priority, TModule, def_method, Method


class Cause(BitEnum, width=31):
    INSTRUCTION_ADDRESS_MISALIGNED = 0
    INSTRUCTION_ADDRESS_FAULT = 1
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


def cause_priority(current_cause: Value, new_cause: Value) -> Value:
    return (
        (new_cause == Cause.BREAKPOINT)
        | (
            (
                (current_cause == Cause.LOAD_ACCESS_FAULT)
                | (current_cause == Cause.STORE_ACCESS_FAULT)
                | (current_cause == Cause.LOAD_PAGE_FAULT)
                | (current_cause == Cause.STORE_PAGE_FAULT)
            )
            & ((new_cause == Cause.LOAD_ADDRESS_MISALIGNED) | (new_cause == Cause.STORE_ADDRESS_MISALIGNED))
        )
        | (
            (current_cause == Cause.ILLEGAL_INSTRUCTION)
            & ((new_cause == Cause.INSTRUCTION_PAGE_FAULT) | (new_cause == Cause.INSTRUCTION_ADDRESS_FAULT))
        )
    )


class ExceptionCauseRegister(Elaboratable):
    def __init__(self, gp: GenParams):
        self.gp = gp

        self.cause = Signal(Cause)
        self.rob_id = Signal(gp.rob_entries_bits)
        self.valid = Signal()

        self.report = Method(i=gp.get(ExceptionRegisterLayouts).report)
        self.clear = Method()

        self.clear.add_conflict(self.report, Priority.LEFT)

        self.rob_order_comparator = Method()

    def elaborate(self, platform):
        m = TModule()

        @def_method(m, self.report)
        def _(cause, rob_id):
            should_write = Signal()

            with m.If(self.valid & (self.rob_id == rob_id)):
                m.d.comb += should_write.eq(cause_priority(current_cause=self.cause, new_cause=cause))
            with m.Elif(self.valid):
                cmp_result = self.rob_order_comparator(m, first_rob_id=rob_id, second_rob_id=self.rob_id)
                m.d.comb += should_write.eq(cmp_result.less)
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
