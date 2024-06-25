from functools import reduce
import operator

from amaranth import *
from amaranth.lib.data import View
from amaranth.utils import exact_log2

from transactron.core import def_method, Priority, TModule
from transactron import Method, Transaction
from coreblocks.params import ICacheParameters
from coreblocks.interface.layouts import ICacheLayouts
from transactron.utils import assign, OneHotSwitchDynamic
from transactron.lib import *
from transactron.lib import logging
from coreblocks.peripherals.bus_adapter import BusMasterInterface

from coreblocks.cache.iface import CacheInterface, CacheRefillerInterface
from transactron.utils.transactron_helpers import make_layout

__all__ = [
    "ICache",
    "ICacheBypass",
]

log = logging.HardwareLogger("frontend.icache")


class ICacheBypass(Elaboratable, CacheInterface):
    def __init__(self, layouts: ICacheLayouts, params: ICacheParameters, bus_master: BusMasterInterface) -> None:
        self.params = params
        self.bus_master = bus_master

        self.issue_req = Method(i=layouts.issue_req)
        self.accept_res = Method(o=layouts.accept_res)
        self.flush = Method()

        if params.words_in_fetch_block != 1:
            raise ValueError("ICacheBypass only supports fetch block size equal to the word size.")

    def elaborate(self, platform):
        m = TModule()

        req_addr = Signal(self.params.addr_width)

        @def_method(m, self.issue_req)
        def _(addr: Value) -> None:
            m.d.sync += req_addr.eq(addr)
            self.bus_master.request_read(
                m,
                addr=addr >> exact_log2(self.params.word_width_bytes),
                sel=C(1).replicate(self.bus_master.params.data_width // self.bus_master.params.granularity),
            )

        @def_method(m, self.accept_res)
        def _():
            res = self.bus_master.get_read_response(m)
            return {
                "fetch_block": res.data,
                "error": res.err,
            }

        @def_method(m, self.flush)
        def _() -> None:
            pass

        return m


class ICache(Elaboratable, CacheInterface):
    """A simple set-associative instruction cache.

    The replacement policy is a pseudo random scheme. Every time a line is trashed,
    we select the next way we write to (we keep one global counter for selecting the next way).

    Refilling a cache line is abstracted away from this module. ICache module needs two methods
    from the refiller `refiller_start`, which is called whenever we need to refill a cache line.
    `refiller_accept` should be ready to be called whenever the refiller has another fetch block
    ready to be written to cache. `refiller_accept` should set `last` bit when either an error
    occurs or the transfer is over. After issuing `last` bit, `refiller_accept` shouldn't be ready
    until the next transfer is started.
    """

    def __init__(self, layouts: ICacheLayouts, params: ICacheParameters, refiller: CacheRefillerInterface) -> None:
        """
        Parameters
        ----------
        layouts : ICacheLayouts
            Instance of ICacheLayouts used to create cache methods.
        params : ICacheParameters
            Instance of ICacheParameters with parameters which should be used to generate
            the cache.
        refiller_start : Method
            A method with input layout ICacheLayouts.start_refill
        refiller_accept : Method
            A method with output layout ICacheLayouts.accept_refill
        """
        self.layouts = layouts
        self.params = params

        self.refiller = refiller

        self.issue_req = Method(i=layouts.issue_req)
        self.accept_res = Method(o=layouts.accept_res)
        self.flush = Method()
        self.flush.add_conflict(self.issue_req, Priority.LEFT)

        self.addr_layout = make_layout(
            ("offset", self.params.offset_bits),
            ("index", self.params.index_bits),
            ("tag", self.params.tag_bits),
        )

        self.perf_loads = HwCounter("frontend.icache.loads", "Number of requests to the L1 Instruction Cache")
        self.perf_hits = HwCounter("frontend.icache.hits")
        self.perf_misses = HwCounter("frontend.icache.misses")
        self.perf_errors = HwCounter("frontend.icache.fetch_errors")
        self.perf_flushes = HwCounter("frontend.icache.flushes")
        self.req_latency = FIFOLatencyMeasurer(
            "frontend.icache.req_latency", "Latencies of cache requests", slots_number=2, max_latency=500
        )

    def deserialize_addr(self, raw_addr: Value) -> dict[str, Value]:
        return {
            "offset": raw_addr[: self.params.offset_bits],
            "index": raw_addr[self.params.index_start_bit : self.params.index_end_bit + 1],
            "tag": raw_addr[-self.params.tag_bits :],
        }

    def serialize_addr(self, addr: View) -> Value:
        return Cat(addr.offset, addr.index, addr.tag)

    def elaborate(self, platform):
        m = TModule()

        m.submodules += [
            self.perf_loads,
            self.perf_hits,
            self.perf_misses,
            self.perf_errors,
            self.perf_flushes,
            self.req_latency,
        ]

        m.submodules.mem = self.mem = ICacheMemory(self.params)
        m.submodules.req_zipper = req_zipper = ArgumentsToResultsZipper(self.addr_layout, self.layouts.accept_res)

        # State machine logic
        needs_refill = Signal()
        refill_finish = Signal()
        refill_error = Signal()
        refill_error_saved = Signal()

        flush_start = Signal()
        flush_start_saved = Signal()
        flush_finish = Signal()

        with Transaction().body(m):
            self.perf_flushes.incr(m, cond=flush_finish)

        with m.FSM(reset="FLUSH") as fsm:
            with m.State("FLUSH"):
                with m.If(flush_finish):
                    m.next = "LOOKUP"

            with m.State("LOOKUP"):
                with m.If(needs_refill):
                    m.next = "REFILL"
                with m.Elif(flush_start | flush_start_saved):
                    m.next = "FLUSH"

            with m.State("REFILL"):
                with m.If(flush_start | flush_start_saved):
                    m.next = "FLUSH"
                with m.Elif(refill_finish):
                    m.next = "LOOKUP"

        # Replacement policy
        way_selector = Signal(self.params.num_of_ways, reset=1)
        with m.If(refill_finish):
            m.d.sync += way_selector.eq(way_selector.rotate_left(1))

        # Fast path - read requests
        mem_read_addr = Signal(self.addr_layout)
        prev_mem_read_addr = Signal(self.addr_layout)
        m.d.comb += assign(mem_read_addr, prev_mem_read_addr)

        mem_read_output_valid = Signal()
        forwarding_response_now = Signal()
        accepting_requests = ~mem_read_output_valid | forwarding_response_now

        refill_line_buffer = Array(
            [
                Signal(
                    make_layout(
                        ("data", 8 * self.params.fetch_block_bytes),
                        ("valid", 1),
                    )
                )
                for _ in range(self.params.fetch_blocks_in_line)
            ]
        )
        refill_tag = Signal(self.params.tag_bits)
        refill_index = Signal(self.params.index_bits)

        with Transaction(name="MemRead").body(
            m, request=fsm.ongoing("LOOKUP") & (mem_read_output_valid | refill_error_saved)
        ):
            req_addr = req_zipper.peek_arg(m)

            tag_hit = [tag_data.valid & (tag_data.tag == req_addr.tag) for tag_data in self.mem.tag_rd_data]
            tag_hit_any = reduce(operator.or_, tag_hit)

            with m.If(tag_hit_any | refill_error_saved):
                m.d.comb += forwarding_response_now.eq(1)
                self.perf_hits.incr(m, cond=tag_hit_any)
                mem_out = Signal(self.params.fetch_block_bytes * 8)
                for i in OneHotSwitchDynamic(m, Cat(tag_hit)):
                    m.d.av_comb += mem_out.eq(self.mem.data_rd_data[i])

                req_zipper.write_results(m, fetch_block=mem_out, error=refill_error_saved)
                m.d.sync += refill_error_saved.eq(0)
                m.d.sync += mem_read_output_valid.eq(0)
            with m.Else():
                self.perf_misses.incr(m)

                m.d.comb += needs_refill.eq(1)

                m.d.sync += refill_tag.eq(req_addr.tag)
                m.d.sync += refill_index.eq(req_addr.index)
                for i in range(self.params.fetch_blocks_in_line):
                    m.d.sync += refill_line_buffer[i].valid.eq(0)

                addr = self.serialize_addr(req_addr)
                aligned_addr = addr & ~((1 << self.params.offset_bits) - 1)
                # TODO: align to fetch block
                log.debug(m, True, "Refilling line 0x{:x} starting from 0x{:x}", aligned_addr, addr)
                self.refiller.start_refill(m, addr=addr)

        # TODO: Further optimization - enable normal lookup on ~refill_hit and tag_hit_any
        with Transaction(name="RefillBufferResponse").body(
            m, request=fsm.ongoing("REFILL") & (mem_read_output_valid | refill_error_saved) & ~flush_start_saved
        ):
            req_addr = req_zipper.peek_arg(m)
            refill_hit = (req_addr.tag == refill_tag) & (req_addr.index == refill_index)
            refill_buffer_hit = refill_hit & refill_line_buffer[req_addr.offset[self.params.fetch_block_bytes_log :]].valid
                
            with m.If(refill_buffer_hit | (refill_hit & refill_error_saved)):
                m.d.comb += forwarding_response_now.eq(1)
                m.d.sync += mem_read_output_valid.eq(0)
                req_zipper.write_results(
                    m, fetch_block=refill_line_buffer[req_addr.offset[self.params.fetch_block_bytes_log :]].data, error=refill_error_saved
                )
                m.d.sync += refill_error_saved.eq(0)

        @def_method(m, self.accept_res)
        def _():
            self.req_latency.stop(m)

            output = req_zipper.read(m)
            return output.results

        @def_method(m, self.issue_req, ready=accepting_requests)
        def _(addr: Value) -> None:
            self.perf_loads.incr(m)
            self.req_latency.start(m)

            deserialized = self.deserialize_addr(addr)
            m.d.comb += assign(mem_read_addr, deserialized)
            m.d.sync += assign(prev_mem_read_addr, deserialized)
            req_zipper.write_args(m, deserialized)

            m.d.sync += mem_read_output_valid.eq(1)

        m.d.comb += [
            self.mem.tag_rd_index.eq(mem_read_addr.index),
            self.mem.data_rd_addr.index.eq(mem_read_addr.index),
            self.mem.data_rd_addr.offset.eq(mem_read_addr.offset),
        ]

        # Flush logic
        flush_index = Signal(self.params.index_bits)
        with m.If(fsm.ongoing("FLUSH")):
            m.d.sync += flush_index.eq(flush_index + 1)
            m.d.sync += flush_start_saved.eq(0)

        @def_method(m, self.flush, ready=accepting_requests)
        def _() -> None:
            log.info(m, True, "Flushing the cache...")
            m.d.sync += flush_index.eq(0)
            m.d.comb += flush_start.eq(1)
            m.d.sync += flush_start_saved.eq(1)

        m.d.comb += flush_finish.eq(flush_index == self.params.num_of_sets - 1)

        # Slow path - data refilling
        with Transaction().body(m):
            ret = self.refiller.accept_refill(m)
            deserialized = self.deserialize_addr(ret.addr)

            self.perf_errors.incr(m, cond=ret.error)

            m.d.top_comb += [
                self.mem.data_wr_addr.index.eq(deserialized["index"]),
                self.mem.data_wr_addr.offset.eq(deserialized["offset"]),
                self.mem.data_wr_data.eq(ret.fetch_block),
            ]

            m.d.comb += self.mem.data_wr_en.eq(1)
            m.d.comb += refill_finish.eq(ret.last)
            m.d.comb += refill_error.eq(ret.error)
            with m.If(ret.error):
                m.d.sync += refill_error_saved.eq(1)

            m.d.sync += refill_line_buffer[deserialized["offset"][self.params.fetch_block_bytes_log :]].data.eq(ret.fetch_block)
            m.d.sync += refill_line_buffer[deserialized["offset"][self.params.fetch_block_bytes_log :]].valid.eq(~ret.error)

        with m.If(fsm.ongoing("FLUSH")):
            m.d.comb += [
                self.mem.way_wr_en.eq(C(1).replicate(self.params.num_of_ways)),
                self.mem.tag_wr_index.eq(flush_index),
                self.mem.tag_wr_data.valid.eq(0),
                self.mem.tag_wr_data.tag.eq(0),
                self.mem.tag_wr_en.eq(1),
            ]
        with m.Else():
            m.d.comb += [
                self.mem.way_wr_en.eq(way_selector),
                self.mem.tag_wr_index.eq(refill_index),
                self.mem.tag_wr_data.valid.eq(~refill_error),
                self.mem.tag_wr_data.tag.eq(refill_tag),
                self.mem.tag_wr_en.eq(refill_finish),
            ]

        return m


class ICacheMemory(Elaboratable):
    """A helper module for managing memories used in the instruction cache.

    In case of an associative cache, all address and write data lines are shared.
    Writes are multiplexed using one-hot `way_wr_en` signal. Read data lines from all
    ways are separately exposed (as an array).

    The data memory is addressed using fetch blocks.
    """

    def __init__(self, params: ICacheParameters) -> None:
        self.params = params

        self.tag_data_layout = make_layout(("valid", 1), ("tag", self.params.tag_bits))

        self.way_wr_en = Signal(self.params.num_of_ways)

        self.tag_rd_index = Signal(self.params.index_bits)
        self.tag_rd_data = Array([Signal(self.tag_data_layout) for _ in range(self.params.num_of_ways)])
        self.tag_wr_index = Signal(self.params.index_bits)
        self.tag_wr_en = Signal()
        self.tag_wr_data = Signal(self.tag_data_layout)

        self.data_addr_layout = make_layout(("index", self.params.index_bits), ("offset", self.params.offset_bits))

        self.fetch_block_bits = params.fetch_block_bytes * 8

        self.data_rd_addr = Signal(self.data_addr_layout)
        self.data_rd_data = Array([Signal(self.fetch_block_bits) for _ in range(self.params.num_of_ways)])
        self.data_wr_addr = Signal(self.data_addr_layout)
        self.data_wr_en = Signal()
        self.data_wr_data = Signal(self.fetch_block_bits)

    def elaborate(self, platform):
        m = TModule()

        for i in range(self.params.num_of_ways):
            way_wr = self.way_wr_en[i]

            tag_mem = Memory(width=len(Value.cast(self.tag_wr_data)), depth=self.params.num_of_sets)
            tag_mem_rp = tag_mem.read_port()
            tag_mem_wp = tag_mem.write_port()
            m.submodules[f"tag_mem_{i}_rp"] = tag_mem_rp
            m.submodules[f"tag_mem_{i}_wp"] = tag_mem_wp

            m.d.comb += [  # remove Value.cast after Amaranth upgrade
                assign(Value.cast(self.tag_rd_data[i]), tag_mem_rp.data),
                tag_mem_rp.addr.eq(self.tag_rd_index),
                tag_mem_wp.addr.eq(self.tag_wr_index),
                assign(tag_mem_wp.data, Value.cast(self.tag_wr_data)),
                tag_mem_wp.en.eq(self.tag_wr_en & way_wr),
            ]

            data_mem = Memory(
                width=self.fetch_block_bits, depth=self.params.num_of_sets * self.params.fetch_blocks_in_line
            )
            data_mem_rp = data_mem.read_port()
            data_mem_wp = data_mem.write_port()
            m.submodules[f"data_mem_{i}_rp"] = data_mem_rp
            m.submodules[f"data_mem_{i}_wp"] = data_mem_wp

            # We address the data RAM using fetch blocks, so we have to
            # discard a few least significant bits from the address.
            rd_addr = Cat(self.data_rd_addr.offset, self.data_rd_addr.index)[self.params.fetch_block_bytes_log :]
            wr_addr = Cat(self.data_wr_addr.offset, self.data_wr_addr.index)[self.params.fetch_block_bytes_log :]

            m.d.comb += [
                self.data_rd_data[i].eq(data_mem_rp.data),
                data_mem_rp.addr.eq(rd_addr),
                data_mem_wp.addr.eq(wr_addr),
                data_mem_wp.data.eq(self.data_wr_data),
                data_mem_wp.en.eq(self.data_wr_en & way_wr),
            ]

        return m
