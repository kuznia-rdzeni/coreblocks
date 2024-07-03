from amaranth import *

from transactron.core import *
from transactron.lib import BasicFifo, Pipe, logging
from transactron.utils import DependencyContext

from coreblocks.params.genparams import GenParams
from coreblocks.frontend.decoder.decode_stage import DecodeStage
from coreblocks.frontend.fetch.fetch import FetchUnit
from coreblocks.frontend.fetch.fetch_target_queue import FetchTargetQueue
from coreblocks.frontend.branch_prediction import BranchPredictionUnit
from coreblocks.cache.icache import ICache, ICacheBypass
from coreblocks.cache.refiller import SimpleCommonBusCacheRefiller
from coreblocks.interface.layouts import *
from coreblocks.interface.keys import FlushICacheKey
from coreblocks.peripherals.bus_adapter import BusMasterInterface


log = logging.HardwareLogger("frontend")


class CoreFrontend(Elaboratable):
    """Frontend of the core.

    Attributes
    ----------
    consume_instr: Method
        Consume a single decoded instruction.
    resume_from_exception: Method
        Resume the frontend from the given PC after an exception.
    resume_from_unsafe: Method
        Resume the frontend from the given PC after an unsafe instruction.
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

        self.bpu = BranchPredictionUnit(self.gen_params)
        self.ftq = FetchTargetQueue(self.gen_params, self.bpu)
        self.fetch = FetchUnit(
            self.gen_params,
            self.icache,
            self.instr_buffer.write,
            self.ftq.consume_fetch_target,
            self.ftq.consume_prediction,
            self.ftq.ifu_writeback,
        )

        self.decode_pipe = Pipe(self.gen_params.get(DecodeLayouts).decoded_instr)

        self.consume_instr = self.decode_pipe.read

        self.resume = self.ftq.stall_ctrl.resume
        self.flush_and_stall = Method()

    def elaborate(self, platform):
        m = TModule()

        if self.icache_refiller:
            m.submodules.icache_refiller = self.icache_refiller
        m.submodules.icache = self.icache

        m.submodules.bpu = self.bpu
        m.submodules.ftq = self.ftq
        m.submodules.fetch = self.fetch
        m.submodules.instr_buffer = self.instr_buffer

        m.submodules.decode_pipe = self.decode_pipe
        m.submodules.decode = DecodeStage(
            gen_params=self.gen_params, get_raw=self.instr_buffer.read, push_decoded=self.decode_pipe.write
        )

        @def_method(m, self.flush_and_stall)
        def _():
            self.ftq.stall(m)
            self.fetch.flush(m)
            self.instr_buffer.clear(m)
            self.decode_pipe.clean(m)

        return m
