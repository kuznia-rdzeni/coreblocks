from amaranth import *
from coreblocks.cache.icache import CacheRefillerInterface
from coreblocks.params import ICacheParameters
from coreblocks.interface.layouts import ICacheLayouts
from coreblocks.peripherals.bus_adapter import BusMasterInterface
from transactron.core import Transaction
from transactron.lib import Forwarder, Method, TModule, def_method

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

        request_now = Signal()
        request_address = Signal(self.bus_master.params.addr_width)

        def request(address):
            m.d.comb += request_now.eq(1)
            m.d.comb += request_address.eq(address)

        with Transaction().body(m, request=request_now):
            self.bus_master.request_read(
                m,
                addr=request_address,
                sel=C(1).replicate(self.bus_master.params.data_width // self.bus_master.params.granularity),
            )

        refill_active = Signal()
        cache_line_address = Signal(self.params.word_width - self.params.offset_bits)

        word_counter = Signal(range(self.params.words_in_line))
        block_buffer = Signal(self.params.word_width * (self.params.words_in_fetch_block - 1))

        # The transaction reads responses from the bus, builds the fetch block and when
        # receives the last word of the fetch block, dispatches it.
        with Transaction().body(m):
            bus_response = self.bus_master.get_read_response(m)

            block = Signal(self.params.fetch_block_bytes * 8)
            m.d.av_comb += block.eq(Cat(block_buffer, bus_response.data))
            m.d.sync += block_buffer.eq(block[self.params.word_width :])

            words_in_fetch_block_log = exact_log2(self.params.words_in_fetch_block)
            current_fetch_block = word_counter[words_in_fetch_block_log:]
            word_in_fetch_block = word_counter[:words_in_fetch_block_log]

            last_word = Signal()
            m.d.av_comb += last_word.eq((word_counter == self.params.words_in_line - 1) | bus_response.err)

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
                    last=last_word,
                )

            word_counter_plus_one = Signal.like(word_counter)
            m.d.av_comb += word_counter_plus_one.eq(word_counter + 1)

            with m.If(last_word):
                m.d.sync += refill_active.eq(0)
            with m.Else():
                request(Cat(word_counter_plus_one, cache_line_address))

            m.d.sync += word_counter.eq(word_counter_plus_one)

        @def_method(m, self.start_refill, ready=~refill_active)
        def _(addr) -> None:
            line_addr = addr[self.params.offset_bits :]
            m.d.sync += cache_line_address.eq(line_addr)

            m.d.sync += word_counter.eq(0)
            m.d.sync += refill_active.eq(1)

            request(Cat(C(0, word_counter.shape()), line_addr))

        @def_method(m, self.accept_refill)
        def _():
            return resp_fwd.read(m)

        return m
