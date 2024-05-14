from amaranth import *

from transactron.core import *
from transactron.lib import BasicFifo, Pipe
from transactron.utils.dependencies import DependencyContext

from coreblocks.params.genparams import GenParams
from coreblocks.frontend.decoder.decode_stage import DecodeStage
from coreblocks.frontend.fetch.fetch import FetchUnit
from coreblocks.cache.icache import ICache, ICacheBypass
from coreblocks.cache.refiller import SimpleCommonBusCacheRefiller
from coreblocks.interface.layouts import *
from coreblocks.interface.keys import BranchVerifyKey, FlushICacheKey
from coreblocks.peripherals.bus_adapter import BusMasterInterface


class CoreFrontend(Elaboratable):
    """Frontend of the core.

    Attributes
    ----------
    inject_instr: Method
        Inject a raw instruction (of type FetchLayouts.raw_instr) directly
        into the instruction buffer.
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

        self.fetch = FetchUnit(self.gen_params, self.icache, self.instr_buffer.write)

        self.decode_pipe = Pipe(self.gen_params.get(DecodeLayouts).decoded_instr)

        self.inject_instr = self.instr_buffer.write
        self.consume_instr = self.decode_pipe.read
        self.resume_from_exception = self.fetch.resume_from_exception
        self.resume_from_unsafe = self.fetch.resume_from_unsafe
        self.stall = Method()

    def elaborate(self, platform):
        m = TModule()

        if self.icache_refiller:
            m.submodules.icache_refiller = self.icache_refiller
        m.submodules.icache = self.icache

        m.submodules.fetch = self.fetch
        m.submodules.instr_buffer = self.instr_buffer

        m.submodules.decode_pipe = self.decode_pipe
        m.submodules.decode = DecodeStage(
            gen_params=self.gen_params, get_raw=self.instr_buffer.read, push_decoded=self.decode_pipe.write
        )

        # TODO: Remove when Branch Predictor implemented
        with Transaction(name="DiscardBranchVerify").body(m):
            read = self.connections.get_dependency(BranchVerifyKey())
            read(m)  # Consume to not block JB Unit

        @def_method(m, self.stall)
        def _():
            self.fetch.stall_exception(m)
            self.instr_buffer.clear(m)
            self.decode_pipe.clean(m)

        return m
