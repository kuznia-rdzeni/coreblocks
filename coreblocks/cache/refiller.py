from amaranth import *
from coreblocks.cache.icache import CacheRefillerInterface
from coreblocks.params import ICacheParameters
from coreblocks.interface.layouts import ICacheLayouts
from coreblocks.peripherals.bus_adapter import BusMasterInterface
from transactron.core import Transaction, Method, TModule, def_method
from transactron.lib import Forwarder

from amaranth.utils import exact_log2


__all__ = ["SimpleCommonBusCacheRefiller"]


class SimpleCommonBusCacheRefiller(Elaboratable, CacheRefillerInterface):
    def __init__(self, layouts: ICacheLayouts, params: ICacheParameters, bus_master: BusMasterInterface):
        self.layouts = layouts
        self.params = params
        self.bus_master = bus_master

        self.start_refill = Method(i=layouts.start_refill)
        self.accept_refill = Method(o=layouts.accept_refill)

    def elaborate(self, platform):
        m = TModule()

        m.submodules.resp_fwd = resp_fwd = Forwarder(self.layouts.accept_refill)

        cache_line_address = Signal(self.params.word_width - self.params.offset_bits)

        refill_active = Signal()
        flushing = Signal()

        sending_requests = Signal()
        req_word_counter = Signal(range(self.params.words_in_line))

        with Transaction().body(m, request=sending_requests):
            self.bus_master.request_read(
                m,
                addr=Cat(req_word_counter, cache_line_address),
                sel=C(1).replicate(self.bus_master.params.data_width // self.bus_master.params.granularity),
            )

            m.d.sync += req_word_counter.eq(req_word_counter + 1)
            with m.If(req_word_counter == (self.params.words_in_line - 1)):
                m.d.sync += sending_requests.eq(0)

        resp_word_counter = Signal(range(self.params.words_in_line))
        block_buffer = Signal(self.params.word_width * (self.params.words_in_fetch_block - 1))

        # The transaction reads responses from the bus, builds the fetch block and when
        # receives the last word of the fetch block, dispatches it.
        with Transaction().body(m):
            bus_response = self.bus_master.get_read_response(m)

            block = Signal(self.params.fetch_block_bytes * 8)
            m.d.av_comb += block.eq(Cat(block_buffer, bus_response.data))
            m.d.sync += block_buffer.eq(block[self.params.word_width :])

            words_in_fetch_block_log = exact_log2(self.params.words_in_fetch_block)
            current_fetch_block = resp_word_counter[words_in_fetch_block_log:]
            word_in_fetch_block = resp_word_counter[:words_in_fetch_block_log]

            with m.If(~flushing):
                with m.If((word_in_fetch_block == self.params.words_in_fetch_block - 1) | bus_response.err):
                    fetch_block_addr = Cat(
                        C(0, exact_log2(self.params.word_width_bytes)),
                        C(0, words_in_fetch_block_log),
                        current_fetch_block,
                        cache_line_address,
                    )

                    resp_fwd.write(
                        m,
                        addr=fetch_block_addr,
                        fetch_block=block,
                        error=bus_response.err,
                        last=(resp_word_counter == self.params.words_in_line - 1) | bus_response.err,
                    )

                with m.If(resp_word_counter == self.params.words_in_line - 1):
                    m.d.sync += refill_active.eq(0)
                with m.Elif(bus_response.err):
                    m.d.sync += sending_requests.eq(0)
                    m.d.sync += flushing.eq(1)

            m.d.sync += resp_word_counter.eq(resp_word_counter + 1)

        with m.If(flushing & (resp_word_counter == req_word_counter)):
            m.d.sync += refill_active.eq(0)
            m.d.sync += flushing.eq(0)

        @def_method(m, self.start_refill, ready=~refill_active)
        def _(addr) -> None:
            m.d.sync += cache_line_address.eq(addr[self.params.offset_bits :])
            m.d.sync += req_word_counter.eq(0)
            m.d.sync += sending_requests.eq(1)

            m.d.sync += resp_word_counter.eq(0)

            m.d.sync += refill_active.eq(1)

        @def_method(m, self.accept_refill)
        def _():
            return resp_fwd.read(m)

        return m
