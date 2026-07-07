from amaranth import *

from transactron.core import *
from transactron.utils.transactron_helpers import make_layout
from transactron.utils import logging
from transactron.lib import Pipe

from coreblocks.params import *
from coreblocks.arch import CfiType
from coreblocks.frontend import FrontendParams
from coreblocks.frontend.bpu.micro_btb import MicroBTB
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

        m.submodules.micro_btb = micro_btb = MicroBTB(self.gen_params)
        m.submodules.pipe = pipe = Pipe(
            layout=make_layout(fields.pc, fields.ftq_ptr, ("entry_idx", self.gen_params.fetch_width_log))
        )

        @def_method(m, self.request)
        def _(pc, ftq_ptr):
            micro_btb.request(m, pc=pc)
            pipe.write(
                m,
                pc=fparams.pc_from_fb(fparams.fb_addr(pc) + 1, 0),
                ftq_ptr=ftq_ptr,
                entry_idx=fparams.fb_instr_idx(pc),
            )

        with Transaction(name="BPU_Stage1").body(m):
            prediction = micro_btb.predict(m)
            stage = pipe.read(m)

            hit = Signal()
            m.d.av_comb += hit.eq(prediction.hit & (prediction.cfi_idx >= stage.entry_idx))

            # On a hit, redirect fetch to the predicted target; otherwise fall through.
            next_pc = Mux(hit, prediction.target, stage.pc)

            pred = Signal(fetch_layouts.bpu_prediction)
            m.d.av_comb += [
                pred.cfi_target.eq(prediction.target),
                pred.cfi_target_valid.eq(hit),
                # Zero the index too on a discarded hit
                pred.cfi_idx.eq(Mux(hit, prediction.cfi_idx, 0)),
                pred.cfi_type.eq(Mux(hit, prediction.cfi_type, CfiType.INVALID)),
                pred.branch_mask.eq(0),
            ]
            self.write_prediction(m, pc=next_pc, ftq_ptr=stage.ftq_ptr, prediction=pred)

        @def_method(m, self.update)
        def _(pc, cfi_target, cfi_idx, cfi_type, taken):
            micro_btb.update(m, pc=pc, target=cfi_target, cfi_idx=cfi_idx, cfi_type=cfi_type, taken=taken)

        @def_method(m, self.flush, nonexclusive=True)
        def _():
            pipe.clear(m)

        return m
