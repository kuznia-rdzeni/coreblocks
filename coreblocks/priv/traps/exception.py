from amaranth import *
from transactron.utils.dependencies import DependencyContext
from coreblocks.params.genparams import GenParams

from coreblocks.arch import ExceptionCause
from coreblocks.interface.layouts import ExceptionRegisterLayouts
from coreblocks.interface.keys import ExceptionReportKey
from transactron.core import TModule, def_method, Method
from transactron.lib.connectors import ConnectTrans
from transactron.lib.fifo import BasicFifo


# NOTE: This function is not used in ExceptionCauseRegister, but may be useful in computing priorities before reporting
def should_update_prioriy(m: TModule, current_cause: Value, new_cause: Value) -> Value:
    # Comparing all priorities would be expensive, this function only checks conditions that could happen in hardware
    _update = Signal()

    # All breakpoint kinds have the highest priority in conflicting cases
    with m.If(new_cause == ExceptionCause.BREAKPOINT):
        m.d.comb += _update.eq(1)

    with m.If(
        ((new_cause == ExceptionCause.INSTRUCTION_PAGE_FAULT) | (new_cause == ExceptionCause.INSTRUCTION_ACCESS_FAULT))
        & (current_cause != ExceptionCause.BREAKPOINT)
    ):
        m.d.comb += _update.eq(1)

    with m.If(
        (new_cause == ExceptionCause.LOAD_ADDRESS_MISALIGNED)
        & ((current_cause == ExceptionCause.LOAD_ACCESS_FAULT) | (current_cause == ExceptionCause.LOAD_PAGE_FAULT))
    ):
        m.d.comb += _update.eq(1)

    with m.If(
        (new_cause == ExceptionCause.STORE_ADDRESS_MISALIGNED)
        & ((current_cause == ExceptionCause.STORE_ACCESS_FAULT) | (current_cause == ExceptionCause.STORE_PAGE_FAULT))
    ):
        m.d.comb += _update.eq(1)

    return _update


class ExceptionCauseRegister(Elaboratable):
    """ExceptionCauseRegister

    Stores parameters of earliest (in instruction order) exception, to save resources in the `ReorderBuffer`.
    All FUs that report exceptions should `report` the details to `ExceptionCauseRegister` and set `exception` bit in
    result data. Exception order is computed in this module. Only one exception can be reported for single instruction,
    exception priorities should be computed locally before calling report.
    If `exception` bit is set in the ROB, `Retirement` stage fetches exception details from this module.
    """

    def __init__(self, gen_params: GenParams, rob_get_indices: Method, fetch_stall_exception: Method):
        self.gen_params = gen_params

        self.cause = Signal(ExceptionCause)
        self.rob_id = Signal(gen_params.rob_entries_bits)
        self.pc = Signal(gen_params.isa.xlen)
        self.valid = Signal()

        self.layouts = gen_params.get(ExceptionRegisterLayouts)

        # Break long combinational paths from single-cycle FUs
        self.fu_report_fifo = BasicFifo(self.layouts.report, 2)
        self.report = self.fu_report_fifo.write
        dm = DependencyContext.get()
        dm.add_dependency(ExceptionReportKey(), self.report)

        self.get = Method(o=self.layouts.get, nonexclusive=True)

        self.clear = Method()

        self.rob_get_indices = rob_get_indices
        self.fetch_stall_exception = fetch_stall_exception

    def elaborate(self, platform):
        m = TModule()

        report = Method(i=self.layouts.report)

        m.submodules.report_fifo = self.fu_report_fifo
        m.submodules.report_connector = ConnectTrans(self.fu_report_fifo.read, report)

        @def_method(m, report)
        def _(cause, rob_id, pc):
            should_write = Signal()

            with m.If(self.valid & (self.rob_id == rob_id)):
                # entry for the same rob_id cannot be overwritten, because its update couldn't be validated
                # in Retirement.
                m.d.av_comb += should_write.eq(0)
            with m.Elif(self.valid):
                rob_start_idx = self.rob_get_indices(m).start
                m.d.av_comb += should_write.eq(
                    (rob_id - rob_start_idx).as_unsigned() < (self.rob_id - rob_start_idx).as_unsigned()
                )
            with m.Else():
                m.d.av_comb += should_write.eq(1)

            with m.If(should_write):
                m.d.sync += self.rob_id.eq(rob_id)
                m.d.sync += self.cause.eq(cause)
                m.d.sync += self.pc.eq(pc)

            m.d.sync += self.valid.eq(1)

            # In case of any reported exception, core will need to be flushed. Fetch can be stalled immediately
            self.fetch_stall_exception(m)

        @def_method(m, self.get)
        def _():
            return {"rob_id": self.rob_id, "cause": self.cause, "pc": self.pc, "valid": self.valid}

        @def_method(m, self.clear)
        def _():
            m.d.sync += self.valid.eq(0)

        return m
