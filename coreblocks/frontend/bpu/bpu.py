from amaranth import *

from transactron.core import *
from transactron.utils.transactron_helpers import make_layout
from transactron.utils import logging
from transactron.lib import Pipe

from coreblocks.params import *
from coreblocks.frontend import FrontendParams
from coreblocks.interface.layouts import CommonLayoutFields
from coreblocks.interface.layouts import BranchPredictionLayouts
from coreblocks.interface.layouts import FetchLayouts

log = logging.HardwareLogger("frontend.bpu")


class BranchPredictionUnit(Elaboratable):
    request: Provided[Method]
    write_prediction: Required[Method]
    update: Provided[Method]
    flush: Provided[Method]

    def __init__(self, gen_params: GenParams) -> None:
        self.gen_params = gen_params
        self.layouts = gen_params.get(BranchPredictionLayouts)

        self.request = Method(i=self.layouts.request)
        self.write_prediction = Method(i=self.layouts.write_prediction)
        self.update = Method(i=self.layouts.update)
        self.flush = Method()

    def elaborate(self, platform):
        m = TModule()

        fparams = self.gen_params.get(FrontendParams)
        fields = self.gen_params.get(CommonLayoutFields)
        fetch_layouts = self.gen_params.get(FetchLayouts)

        m.submodules.pipe = pipe = Pipe(layout=make_layout(fields.pc, fields.ftq_ptr))

        @def_method(m, self.request)
        def _(pc, ftq_ptr):
            pipe.write(m, pc=fparams.pc_from_fb(fparams.fb_addr(pc) + 1, 0), ftq_ptr=ftq_ptr)

        with Transaction(name="BPU_Stage1").body(m):
            stage = pipe.read(m)

            # There are no sub-predictors yet - always predict a fall-through.
            pred = Signal(fetch_layouts.bpu_prediction)
            self.write_prediction(m, pc=stage.pc, ftq_ptr=stage.ftq_ptr, prediction=pred)

        @def_method(m, self.update)
        def _(pc, cfi_target, cfi_idx, cfi_type, taken, mispredict):
            pass

        @def_method(m, self.flush, nonexclusive=True)
        def _():
            pipe.clear(m)

        return m
