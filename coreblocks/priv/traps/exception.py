from amaranth import *
from transactron.utils.dependencies import DependencyContext
from coreblocks.params.genparams import GenParams

from coreblocks.arch import ExceptionCause
from coreblocks.interface.layouts import ExceptionRegisterLayouts
from coreblocks.interface.keys import ActiveTagsKey, ExceptionReportKey
from transactron.core import TModule, def_method, Method, Transaction
from transactron.lib.connectors import ConnectTrans
from transactron.lib.fifo import BasicFifo


class ExceptionInformationRegister(Elaboratable):
    """ExceptionInformationRegister

    Stores parameters of earliest (in instruction order) exception, to save resources in the `ReorderBuffer`.
    All FUs that report exceptions should `report` the details to `ExceptionCauseRegister` and set `exception` bit in
    result data. Exception order is computed in this module. Only one exception can be reported for single instruction,
    exception priorities should be computed locally before calling report.
    If `exception` bit is set in the ROB, `Retirement` stage fetches exception details from this module.
    """

    def __init__(self, gen_params: GenParams, rob_get_indices: Method):
        self.gen_params = gen_params

        self.cause = Signal(ExceptionCause)
        self.rob_id = Signal(gen_params.rob_entries_bits)
        self.pc = Signal(gen_params.isa.xlen)
        self.mtval = Signal(gen_params.isa.xlen)
        self.tag = Signal(gen_params.tag_bits)
        self.valid = Signal()

        self.layouts = gen_params.get(ExceptionRegisterLayouts)

        self.report = Method(i=self.layouts.report)

        self.clears: list[Method] = []

        # Break long combinational paths from single-cycle FUs
        def call_report():
            report_fifo = BasicFifo(self.layouts.report, 2)
            report_connector = ConnectTrans(report_fifo.read, self.report)
            self.clears.append(report_fifo.clear)
            added = False

            def call(m: TModule, **kwargs):
                nonlocal added
                if not added:
                    m.submodules += [report_fifo, report_connector]
                    added = True
                return report_fifo.write(m, **kwargs)

            return call

        self.dm = DependencyContext.get()
        self.dm.add_dependency(ExceptionReportKey(), call_report)

        self.get = Method(o=self.layouts.get)

        self.clear = Method()

        self.rob_get_indices = rob_get_indices

    def elaborate(self, platform):
        m = TModule()

        active_tags_m = self.dm.get_dependency(ActiveTagsKey())
        active_tags = Signal(active_tags_m.layout_out)
        with Transaction().body(m):
            m.d.comb += active_tags.eq(active_tags_m(m))

        with m.If(~active_tags.active_tags[self.tag]):
            # we can safely invalidate all exceptions (the entry) in case of rollback, because rollback invalidates
            # suffix of (youngest) instructions. If the current entry was in that suffix, it means that no older
            # instructions (priority on rob_id selection), including all that remain valid, have raised any exception.
            # Tag can be invalidated only as an effect of rollback.
            m.d.sync += self.valid.eq(0)

        @def_method(m, self.report)
        def _(cause, rob_id, pc, tag, mtval):
            should_write = Signal()

            with m.If(~active_tags.active_tags[tag]):
                # ignore inactive instructions
                m.d.comb += should_write.eq(0)
            with m.Elif(self.valid & (self.rob_id == rob_id)):
                # entry for the same rob_id cannot be overwritten, because its update couldn't be validated
                # in Retirement.
                m.d.comb += should_write.eq(0)
            with m.Elif(self.valid):
                rob_start_idx = self.rob_get_indices(m).start
                m.d.comb += should_write.eq(
                    (rob_id - rob_start_idx).as_unsigned() < (self.rob_id - rob_start_idx).as_unsigned()
                )
            with m.Else():
                m.d.comb += should_write.eq(1)

            with m.If(should_write):  # TODO: convert to dict
                m.d.sync += self.rob_id.eq(rob_id)
                m.d.sync += self.cause.eq(cause)
                m.d.sync += self.pc.eq(pc)
                m.d.sync += self.tag.eq(tag)
                m.d.sync += self.mtval.eq(mtval)

            m.d.sync += self.valid.eq(1)

        @def_method(m, self.get, nonexclusive=True)
        def _():
            return {
                "rob_id": self.rob_id,
                "cause": self.cause,
                "pc": self.pc,
                "tag": self.tag,
                "mtval": self.mtval,
                "valid": self.valid,
            }

        @def_method(m, self.clear)
        def _():
            m.d.sync += self.valid.eq(0)
            for clear in self.clears:
                clear(m)
            del self.clears  # exception will be raised if new fifos are created later

        return m
