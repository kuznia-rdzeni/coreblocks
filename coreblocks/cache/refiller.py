from amaranth import *
from coreblocks.cache.iface import CacheRefillerInterface, DataCacheRefillerInterface
from coreblocks.params import ICacheParameters, DCacheParameters
from coreblocks.interface.layouts import ICacheLayouts, DCacheLayouts
from coreblocks.peripherals.bus_adapter import BusMasterInterface
from transactron.core import Transaction, Method, TModule, def_method
from transactron.lib import Forwarder

from amaranth.utils import exact_log2


__all__ = ["SimpleCommonBusCacheRefiller", "SimpleCommonBusDataCacheRefiller"]


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

        with Transaction().body(m, ready=sending_requests):
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


class SimpleCommonBusDataCacheRefiller(Elaboratable, DataCacheRefillerInterface):
    def __init__(self, layouts: DCacheLayouts, params: DCacheParameters, bus_master: BusMasterInterface):
        if params.word_width != bus_master.params.data_width:
            raise ValueError("Data cache word width must match bus data width.")
        if bus_master.params.granularity != 8:
            raise ValueError("Data cache refiller expects byte-granular bus selects.")

        self.layouts = layouts
        self.params = params
        self.bus_master = bus_master

        self.start_refill = Method(i=layouts.start_refill)
        self.accept_refill = Method(o=layouts.accept_refill)

        self.start_writeback = Method(i=layouts.start_writeback)
        self.accept_writeback = Method(o=layouts.accept_writeback)
        self.get_writeback_data = Method(o=layouts.provide_writeback_data)

    def elaborate(self, platform):
        m = TModule()

        m.submodules.refill_resp_fwd = refill_resp_fwd = Forwarder(self.layouts.accept_refill)
        m.submodules.writeback_resp_fwd = writeback_resp_fwd = Forwarder(self.layouts.accept_writeback)

        line_addr = Signal(self.params.addr_width - self.params.offset_bits)
        word_idx = Signal(range(self.params.words_in_line))
        writeback_error = Signal()

        word_bytes_log = exact_log2(self.params.word_width_bytes)
        full_sel = C(1).replicate(self.bus_master.params.data_width // self.bus_master.params.granularity)
        bus_word_addr = Cat(word_idx, line_addr)
        byte_word_addr = Cat(C(0, word_bytes_log), word_idx, line_addr)
        last_word = word_idx == self.params.words_in_line - 1

        start_refill_req = Signal()
        start_writeback_req = Signal()
        bus_read_request_done = Signal()
        bus_read_done = Signal()
        bus_read_error = Signal()
        bus_write_request_done = Signal()
        bus_write_done = Signal()

        with m.FSM(init="IDLE") as fsm:
            with m.State("IDLE"):
                with m.If(start_refill_req):
                    m.next = "REFILL_REQ"
                with m.Elif(start_writeback_req):
                    m.next = "WRITEBACK_REQ"

            with m.State("REFILL_REQ"):
                with m.If(bus_read_request_done):
                    m.next = "REFILL_RESP"

            with m.State("REFILL_RESP"):
                with m.If(bus_read_done):
                    with m.If(bus_read_error | last_word):
                        m.next = "IDLE"
                    with m.Else():
                        m.next = "REFILL_REQ"

            with m.State("WRITEBACK_REQ"):
                with m.If(bus_write_request_done):
                    m.next = "WRITEBACK_RESP"

            with m.State("WRITEBACK_RESP"):
                with m.If(bus_write_done):
                    with m.If(last_word):
                        m.next = "IDLE"
                    with m.Else():
                        m.next = "WRITEBACK_REQ"

        with Transaction(name="DCacheRefillRequest").body(m, ready=fsm.ongoing("REFILL_REQ")):
            self.bus_master.request_read(
                m,
                addr=bus_word_addr,
                sel=full_sel,
            )
            m.d.comb += bus_read_request_done.eq(1)

        with Transaction(name="DCacheRefillResponse").body(m, ready=fsm.ongoing("REFILL_RESP")):
            bus_response = self.bus_master.get_read_response(m)
            m.d.comb += [
                bus_read_done.eq(1),
                bus_read_error.eq(bus_response.err),
            ]
            refill_resp_fwd.write(
                m,
                addr=byte_word_addr,
                data=bus_response.data,
                error=bus_response.err,
                last=bus_response.err | last_word,
            )

            with m.If(~bus_response.err & ~last_word):
                m.d.sync += word_idx.eq(word_idx + 1)

        with Transaction(name="DCacheWritebackRequest").body(m, ready=fsm.ongoing("WRITEBACK_REQ")):
            data = self.get_writeback_data(m)
            self.bus_master.request_write(
                m,
                addr=bus_word_addr,
                data=data.data,
                sel=full_sel,
            )
            m.d.comb += bus_write_request_done.eq(1)

        with Transaction(name="DCacheWritebackResponse").body(m, ready=fsm.ongoing("WRITEBACK_RESP")):
            bus_response = self.bus_master.get_write_response(m)
            m.d.comb += bus_write_done.eq(1)

            with m.If(last_word):
                writeback_resp_fwd.write(m, error=writeback_error | bus_response.err)
            with m.Else():
                m.d.sync += [
                    writeback_error.eq(writeback_error | bus_response.err),
                    word_idx.eq(word_idx + 1),
                ]

        @def_method(m, self.start_refill, ready=fsm.ongoing("IDLE"))
        def _(addr) -> None:
            m.d.comb += start_refill_req.eq(1)
            m.d.sync += [
                line_addr.eq(addr[self.params.offset_bits :]),
                word_idx.eq(0),
            ]

        @def_method(m, self.accept_refill)
        def _():
            return refill_resp_fwd.read(m)

        @def_method(m, self.start_writeback, ready=fsm.ongoing("IDLE"))
        def _(addr) -> None:
            m.d.comb += start_writeback_req.eq(1)
            m.d.sync += [
                line_addr.eq(addr[self.params.offset_bits :]),
                word_idx.eq(0),
                writeback_error.eq(0),
            ]

        @def_method(m, self.accept_writeback)
        def _():
            return writeback_resp_fwd.read(m)

        return m
