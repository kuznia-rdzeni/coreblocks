from amaranth import *

from transactron.core import *
from transactron.utils.transactron_helpers import make_layout
from transactron.utils import logging, MethodLayout

from coreblocks.params import *
from coreblocks.frontend import FrontendParams
from coreblocks.interface.layouts import CommonLayoutFields
from coreblocks.interface.layouts import BranchPredictionLayouts

log = logging.HardwareLogger("frontend.bpu")


class _Pipe(Elaboratable):
    # TODO: 'clear' method of Pipe creates conflicts with other methods. This blocking behavior is not
    # needed there and creates a lot of unnecessary logic and delays. Remove this once the clear method
    # is non-blocking

    def __init__(self, layout: MethodLayout):
        self.read = Method(o=layout)
        self.write = Method(i=layout)
        self.clear = Method()

    def elaborate(self, platform):
        m = TModule()

        reg = Signal.like(self.read.data_out)
        reg_valid = Signal()

        self.read.schedule_before(self.write)  # to avoid combinational loops

        @def_method(m, self.read, ready=reg_valid)
        def _():
            m.d.sync += reg_valid.eq(0)
            return reg

        @def_method(m, self.write, ready=~reg_valid | self.read.run)
        def _(arg):
            m.d.sync += reg.eq(arg)
            m.d.sync += reg_valid.eq(1)

        @def_method(m, self.clear)
        def _():
            m.d.sync += reg_valid.eq(0)

        return m


class BranchPredictionUnit(Elaboratable):
    request: Provided[Method]
    write_prediction: Required[Method]
    flush: Provided[Method]

    def __init__(self, gen_params: GenParams) -> None:
        self.gen_params = gen_params
        self.layouts = gen_params.get(BranchPredictionLayouts)

        self.request = Method(i=self.layouts.request)
        self.write_prediction = Method(i=self.layouts.write_prediction)
        self.flush = Method()

    def elaborate(self, platform):
        m = TModule()

        fparams = self.gen_params.get(FrontendParams)
        fields = self.gen_params.get(CommonLayoutFields)

        m.submodules.pipe = pipe = _Pipe(layout=make_layout(fields.pc, fields.ftq_ptr))

        @def_method(m, self.request)
        def _(pc, ftq_ptr):
            pipe.write(m, pc=fparams.pc_from_fb(fparams.fb_addr(pc) + 1, 0), ftq_ptr=ftq_ptr)

        with Transaction(name="BPU_Stage1").body(m):
            self.write_prediction(m, pipe.read(m))

        @def_method(m, self.flush, nonexclusive=True)
        def _():
            pipe.clear(m)

        return m
