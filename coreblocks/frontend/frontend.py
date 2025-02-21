from amaranth import *

from transactron.core import *
from transactron.lib import BasicFifo, Pipe
from transactron.utils.dependencies import DependencyContext

from coreblocks.params.genparams import GenParams
from coreblocks.frontend.decoder.decode_stage import DecodeStage
from coreblocks.frontend.fetch.fetch import FetchUnit
from coreblocks.frontend.stall_controller import StallController
from coreblocks.cache.icache import ICache, ICacheBypass
from coreblocks.cache.refiller import SimpleCommonBusCacheRefiller
from coreblocks.interface.layouts import *
from coreblocks.interface.keys import BranchVerifyKey, FlushICacheKey, PredictedJumpTargetKey
from coreblocks.peripherals.bus_adapter import BusMasterInterface


class CoreFrontend(Elaboratable):
    """Frontend of the core.

    Attributes
    ----------
    consume_instr: Method
        Consume a single decoded instruction.
    resume_from_exception: Method
        Resume the frontend from the given PC after an exception.
    stall: Method
        Stall and flush the frontend.
    """

    def __init__(self, *, gen_params: GenParams, instr_bus: BusMasterInterface):
        self.gen_params = gen_params
        self.connections = DependencyContext.get()

        self.instr_buffer = BasicFifo(self.gen_params.get(FetchLayouts).raw_instr, self.gen_params.instr_buffer_size)

        cache_layouts = self.gen_params.get(ICacheLayouts)
        if gen_params.icache_params.enable:
            self.icache_refiller = SimpleCommonBusCacheRefiller(cache_layouts, self.gen_params.icache_params, instr_bus)
            self.icache = ICache(cache_layouts, self.gen_params.icache_params, self.icache_refiller)
        else:
            self.icache = ICacheBypass(cache_layouts, gen_params.icache_params, instr_bus)

        self.connections.add_dependency(FlushICacheKey(), self.icache.flush)

        self.stall_ctrl = StallController(self.gen_params)

        self.fetch = FetchUnit(
            self.gen_params,
            self.icache,
            self.instr_buffer.write,
            self.stall_ctrl.stall_guard,
            self.stall_ctrl.stall_unsafe,
        )

        self.decode_pipe = Pipe(self.gen_params.get(DecodeLayouts).decoded_instr)

        # TODO: move and implement these methods
        jb_layouts = self.gen_params.get(JumpBranchLayouts)
        self.target_pred_req = Method(i=jb_layouts.predicted_jump_target_req)
        self.target_pred_resp = Method(o=jb_layouts.predicted_jump_target_resp)
        DependencyContext.get().add_dependency(PredictedJumpTargetKey(), (self.target_pred_req, self.target_pred_resp))

        self.consume_instr = self.decode_pipe.read
        self.resume_from_exception = self.stall_ctrl.resume_from_exception
        self.stall = Method()

    def elaborate(self, platform):
        m = TModule()

        if self.gen_params.icache_params.enable:
            m.submodules.icache_refiller = self.icache_refiller
        m.submodules.icache = self.icache

        m.submodules.fetch = self.fetch
        m.submodules.instr_buffer = self.instr_buffer

        m.submodules.decode_pipe = self.decode_pipe
        m.submodules.decode = decode = DecodeStage(gen_params=self.gen_params)
        decode.get_raw.proxy(m, self.instr_buffer.read)
        decode.push_decoded.proxy(m, self.decode_pipe.write)

        m.submodules.stall_ctrl = self.stall_ctrl

        self.stall_ctrl.redirect_frontend.proxy(m, self.fetch.redirect)

        # TODO: Remove when Branch Predictor implemented
        with Transaction(name="DiscardBranchVerify").body(m):
            read = self.connections.get_dependency(BranchVerifyKey())
            read(m)  # Consume to not block JB Unit

        @def_method(m, self.target_pred_req)
        def _():
            pass

        @def_method(m, self.target_pred_resp)
        def _(arg):
            return {"valid": 0, "cfi_target": 0}

        @def_method(m, self.stall)
        def _():
            self.stall_ctrl.stall_exception(m)
            self.fetch.flush(m)
            self.instr_buffer.clear(m)
            self.decode_pipe.clean(m)

        return m
