from amaranth import *

from transactron.core import Transaction, TModule
from transactron.lib import FIFO, MethodMap, MethodProduct
from transactron.utils.dependencies import DependencyContext

from coreblocks.params.genparams import GenParams
from coreblocks.frontend.decoder.decode_stage import DecodeStage
from coreblocks.frontend.fetch.fetch import FetchUnit
from coreblocks.cache.icache import ICache, ICacheBypass
from coreblocks.cache.refiller import SimpleCommonBusCacheRefiller
from coreblocks.priv.traps.instr_counter import CoreInstructionCounter
from coreblocks.interface.layouts import *
from coreblocks.interface.keys import BranchVerifyKey, FlushICacheKey
from coreblocks.peripherals.bus_adapter import BusMasterInterface


class CoreFrontend(Elaboratable):
    def __init__(self, *, gen_params: GenParams, instr_bus: BusMasterInterface):
        self.gen_params = gen_params

        self.connections = DependencyContext.get()

        self.instr_bus = instr_bus

        self.core_counter = CoreInstructionCounter(self.gen_params)

        # make fetch_continue visible outside the core for injecting instructions
        self.fifo_fetch = FIFO(self.gen_params.get(FetchLayouts).raw_instr, 2)

        drop_args_transform = (self.gen_params.get(FetchLayouts).raw_instr, lambda _a, _b: {})
        self.core_counter_increment_discard_map = MethodMap(
            self.core_counter.increment, i_transform=drop_args_transform
        )
        self.fetch_continue = MethodProduct([self.fifo_fetch.write, self.core_counter_increment_discard_map.method])

        cache_layouts = self.gen_params.get(ICacheLayouts)
        if gen_params.icache_params.enable:
            self.icache_refiller = SimpleCommonBusCacheRefiller(cache_layouts, self.gen_params.icache_params, instr_bus)
            self.icache = ICache(cache_layouts, self.gen_params.icache_params, self.icache_refiller)
        else:
            self.icache = ICacheBypass(cache_layouts, gen_params.icache_params, instr_bus)

        self.connections.add_dependency(FlushICacheKey(), self.icache.flush)

        self.fetch = FetchUnit(self.gen_params, self.icache, self.fetch_continue.method)

        self.fifo_decode = FIFO(self.gen_params.get(DecodeLayouts).decoded_instr, 2)

    def elaborate(self, platform):
        m = TModule()

        if self.icache_refiller:
            m.submodules.icache_refiller = self.icache_refiller
        m.submodules.icache = self.icache

        m.submodules.fetch_continue = self.fetch_continue
        m.submodules.fetch = self.fetch
        m.submodules.fifo_fetch = self.fifo_fetch
        m.submodules.core_counter = self.core_counter
        m.submodules.args_discard_map = self.core_counter_increment_discard_map

        m.submodules.fifo_decode = self.fifo_decode
        m.submodules.decode = DecodeStage(
            gen_params=self.gen_params, get_raw=self.fifo_fetch.read, push_decoded=self.fifo_decode.write
        )

        # TODO: Remove when Branch Predictor implemented
        with Transaction(name="DiscardBranchVerify").body(m):
            read = self.connections.get_dependency(BranchVerifyKey())
            read(m)  # Consume to not block JB Unit

        return m
