from amaranth import *
from transactron import Provided, Transaction
from transactron.utils.dependencies import DependencyContext
from coreblocks.params.genparams import GenParams

from coreblocks.interface.layouts import ExceptionInformationRegisterLayouts, ROBLayouts
from coreblocks.interface.keys import ActiveTagsKey, ExceptionReportKey
from transactron.core import Required, TModule, def_method, Method
from transactron.lib.connectors import ConnectTrans
from transactron.lib.fifo import BasicFifo


class ExceptionInformationRegister(Elaboratable):
    """ExceptionInformationRegister

    Stores parameters of oldest (in instruction order) exception, to save resources in the `ReorderBuffer`.
    All FUs that report exceptions should `report` the details to `ExceptionInformationRegister` and set `exception` bit
    in result data. Exception order is computed in this module. Only one exception can be reported for single
    instruction, exception priorities should be computed locally before calling report.
    If `exception` bit is set in the ROB, `Retirement` stage fetches exception details from this module.
    It will automatically track when a tag is invalidated to keep only data from a current speculation path.
    """

    get: Provided[Method]
    report: Provided[Method]
    rob_get_indices: Required[Method]

    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params

        self.layouts = gen_params.get(ExceptionInformationRegisterLayouts)

        self.data = Signal(self.layouts.data)
        self.valid = Signal()

        self.report = Method(i=self.layouts.report)

        self._clears: list[Method] = []

        # Break long combinational paths from single-cycle FUs
        def call_report():
            report_fifo = BasicFifo(self.layouts.report, 2)
            report_connector = ConnectTrans.create(report_fifo.read, self.report)
            self._clears.append(report_fifo.clear)
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

        self.rob_get_indices = Method(o=gen_params.get(ROBLayouts).get_indices)

    def elaborate(self, platform):
        m = TModule()

        with Transaction().body(m):
            active_tags = self.dm.get_dependency(ActiveTagsKey())(m).active_tags

        with m.If(~active_tags[self.data.tag]):
            # If stored exception got invalidated (rolled-back):
            # rollbacks disard suffix of instructions - it means there was no reported exception
            # on any older instruction, and all younger ones are discarded. We can safely remove the entry.
            m.d.sync += self.valid.eq(0)

        @def_method(m, self.report)
        def _(arg):
            should_write = Signal()

            with m.If(~active_tags[arg.tag] | (self.valid & (arg.rob_id == self.data.rob_id))):
                # entry for the same rob_id cannot be overwritten, because its update couldn't be validated
                # in Retirement.
                m.d.comb += should_write.eq(0)
            with m.Elif(self.valid):
                rob_start_idx = self.rob_get_indices(m).start
                m.d.comb += should_write.eq(
                    (arg.rob_id - rob_start_idx).as_unsigned() < (self.data.rob_id - rob_start_idx).as_unsigned()
                )
            with m.Else():
                m.d.comb += should_write.eq(1)

            with m.If(should_write):
                m.d.sync += self.data.eq(arg)
                m.d.sync += self.valid.eq(1)

        @def_method(m, self.get, nonexclusive=True)
        def _():
            return {"data": self.data, "valid": self.valid}

        @def_method(m, self.clear)
        def _():
            m.d.sync += self.valid.eq(0)
            for clear in self._clears:
                clear(m)
            del self._clears  # exception will be raised if new fifos are created later

        return m
