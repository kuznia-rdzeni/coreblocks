from coreblocks.params import ICacheLayouts, ICacheParameters
from coreblocks.peripherals.wishbone import WishboneMaster
from transactron import Method, Transaction
from transactron.core import TModule, def_method
from transactron.lib import Forwarder

from amaranth import Cat, Elaboratable, Repl, Signal
from amaranth.utils import log2_int

from .iface import CacheRefillerInterface


class SimpleWBCacheRefiller(Elaboratable, CacheRefillerInterface):
    def __init__(self, layouts: ICacheLayouts, params: ICacheParameters, wb_master: WishboneMaster):
        self.params = params
        self.wb_master = wb_master

        self.start_refill = Method(i=layouts.start_refill)
        self.accept_refill = Method(o=layouts.accept_refill)

    def elaborate(self, platform):
        m = TModule()

        refill_address = Signal(self.params.word_width - self.params.offset_bits)
        refill_active = Signal()
        word_counter = Signal(range(self.params.words_in_block))

        m.submodules.address_fwd = address_fwd = Forwarder(
            [("word_counter", word_counter.shape()), ("refill_address", refill_address.shape())]
        )

        with Transaction().body(m):
            address = address_fwd.read(m)
            self.wb_master.request(
                m,
                addr=Cat(address["word_counter"], address["refill_address"]),
                data=0,
                we=0,
                sel=Repl(1, self.wb_master.wb_params.data_width // self.wb_master.wb_params.granularity),
            )

        @def_method(m, self.start_refill, ready=~refill_active)
        def _(addr) -> None:
            address = addr[self.params.offset_bits :]
            m.d.sync += refill_address.eq(address)
            m.d.sync += refill_active.eq(1)
            m.d.sync += word_counter.eq(0)

            address_fwd.write(m, word_counter=0, refill_address=address)

        @def_method(m, self.accept_refill, ready=refill_active)
        def _():
            fetched = self.wb_master.result(m)

            last = (word_counter == (self.params.words_in_block - 1)) | fetched.err

            next_word_counter = Signal.like(word_counter)
            m.d.top_comb += next_word_counter.eq(word_counter + 1)

            m.d.sync += word_counter.eq(next_word_counter)
            with m.If(last):
                m.d.sync += refill_active.eq(0)
            with m.Else():
                address_fwd.write(m, word_counter=next_word_counter, refill_address=refill_address)

            return {
                "addr": Cat(Repl(0, log2_int(self.params.word_width_bytes)), word_counter, refill_address),
                "data": fetched.data,
                "error": fetched.err,
                "last": last,
            }

        return m
