from amaranth import *
from amaranth.lib.data import View
import amaranth.lib.memory as memory
from amaranth.utils import exact_log2

from transactron.core import Priority, TModule
from transactron import Method, def_method, Transaction
from coreblocks.params import DCacheParameters
from transactron.utils import assign
from transactron.lib import *
from transactron.lib import logging

from coreblocks.cache.iface import CacheInterface, DataCacheRefillerInterface
from transactron.utils.transactron_helpers import make_layout

__all__ = [
    "DCache",
]

from coreblocks.interface.layouts import DCacheLayouts

log = logging.HardwareLogger("backend.dcache")


class DCache(Elaboratable, CacheInterface):
    """A simple write-back data cache

    Single-core design — no coherence protocol.

    Replacement policy: pseudo-random round-robin (same as ICache).
    """

    def __init__(self, layouts: DCacheLayouts, params, refiller: DataCacheRefillerInterface) -> None:
        """
        Parameters
        ----------
        layouts : DCacheLayouts
            Layouts for D-cache methods.
        params : DCacheParameters
            Cache geometry and configuration.
        refiller : CacheRefillerInterface
            Refiller with writeback support for dirty line eviction.
        """
        self.layouts = layouts
        self.params = params
        self.refiller = refiller

        # Methods
        self.issue_req = Method(i=layouts.issue_req)
        self.accept_res = Method(o=layouts.accept_res)

        self.flush = Method()
        self.flush.add_conflict(self.issue_req, Priority.LEFT)

        # Method called by refiller AFTER cache started writeback (called start_writeback method in refiller)
        self.provide_writeback_data = Method(o=layouts.provide_writeback_data)

        self.addr_layout = make_layout(
            ("offset", self.params.offset_bits),
            ("index", self.params.index_bits),
            ("tag", self.params.tag_bits),
        )

        self.perf_loads = HwCounter("backend.dcache.loads")
        self.perf_stores = HwCounter("backend.dcache.stores")
        self.perf_hits = HwCounter("backend.dcache.hits")
        self.perf_misses = HwCounter("backend.dcache.misses")
        self.perf_writebacks = HwCounter("backend.dcache.writebacks")
        self.perf_errors = HwCounter("backend.dcache.errors")
        self.perf_flushes = HwCounter("backend.dcache.flushes")

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
            self.perf_stores,
            self.perf_hits,
            self.perf_misses,
            self.perf_writebacks,
            self.perf_errors,
            self.perf_flushes,
        ]

        m.submodules.mem = self.mem = DCacheMemory(self.params)

        rr_way = Signal(range(self.params.num_of_ways))  # Round-robin state
        rr_used = Signal()

        flush_start = Signal()
        flush_finish = Signal()
        needs_writeback = Signal()  # if we missed and victim is dirty, writeback the victim and load new line
        needs_refill = Signal()
        refill_finish = Signal()
        writeback_done_error = Signal()
        writeback_done_flush = Signal()
        writeback_done_refill = Signal()

        wb_way = Signal(range(self.params.num_of_ways))
        wb_index = Signal(self.params.index_bits)
        wb_word_counter = Signal(range(self.params.words_in_line))

        wb_triggered_by_flush = Signal()
        flush_writeback_pending = Signal()

        # Request/response communication (lookup)
        pending_req = Signal(self.layouts.issue_req)
        pending_req_valid = Signal()
        lookup_addr = Signal(self.addr_layout)
        lookup_valid = Signal()
        res_reg = Signal(self.layouts.accept_res)
        res_valid = Signal()

        # Refill state
        refill_addr = Signal(self.addr_layout)
        refill_way = Signal(range(self.params.num_of_ways))
        refill_error = Signal()

        with m.FSM(init="FLUSH") as fsm:
            with m.State("FLUSH"):
                with m.If(flush_writeback_pending):
                    m.next = "WRITEBACK"
                with m.Elif(flush_finish):
                    m.next = "LOOKUP"

            with m.State("LOOKUP"):
                with m.If(flush_start):
                    m.next = "FLUSH"
                with m.Elif(needs_writeback):
                    m.next = "WRITEBACK"
                with m.Elif(needs_refill):
                    m.next = "REFILL"

            with m.State("REFILL"):
                with m.If(refill_finish):
                    m.next = "LOOKUP"

            with m.State("WRITEBACK"):
                with m.If(writeback_done_error):
                    with m.If(wb_triggered_by_flush):
                        m.d.sync += [
                            wb_triggered_by_flush.eq(0),
                            flush_writeback_pending.eq(0),
                        ]
                    m.next = "LOOKUP"
                with m.Elif(writeback_done_flush):
                    m.d.sync += [
                        wb_triggered_by_flush.eq(0),
                        flush_writeback_pending.eq(0),
                    ]
                    m.next = "FLUSH"
                with m.Elif(writeback_done_refill):
                    m.next = "REFILL"

        with m.If(fsm.ongoing("LOOKUP") & pending_req_valid & ~lookup_valid & ~res_valid):
            m.d.sync += lookup_valid.eq(1)

        # ------------- FLUSH -------
        # Iterates through all sets, checks dirty bits, starts writeback if needed, then invalidates.
        # 2 cycles per set: cycle 1 = SRAM read (wait), cycle 2 = process tag_rd_data.
        # TODO: optimize to 1 cycle per set

        flush_index = Signal(self.params.index_bits)
        flush_data_valid = Signal()  # high when tag_rd_data is valid for current flush_index

        # SRAM read latency: wait 1 cycle for data
        with m.If(fsm.ongoing("FLUSH") & ~flush_data_valid):
            m.d.sync += flush_data_valid.eq(1)

        with m.If(~fsm.ongoing("FLUSH")):
            m.d.sync += flush_data_valid.eq(0)

        # Connect SRAM read address to flush_index during FLUSH
        with m.If(fsm.ongoing("FLUSH")):
            m.d.comb += self.mem.tag_rd_index.eq(flush_index)

        @def_method(m, self.flush, ready=fsm.ongoing("LOOKUP"))
        def _():
            log.info(m, True, "Flushing the cache...")
            m.d.sync += flush_index.eq(0)
            m.d.sync += flush_data_valid.eq(0)
            m.d.comb += flush_start.eq(1)

        with Transaction(name="Flush").body(m, ready=fsm.ongoing("FLUSH") & flush_data_valid):
            # tag_rd_data is valid for current flush_index

            any_dirty = Signal()
            dirty_way = Signal(range(self.params.num_of_ways))

            for i in range(self.params.num_of_ways):
                tag_data = self.mem.tag_rd_data[i]
                with m.If(tag_data.valid & tag_data.dirty):
                    m.d.comb += any_dirty.eq(1)
                    m.d.comb += dirty_way.eq(i)

            with m.If(any_dirty):
                # Writeback the dirty way, then come back to re-check this set
                wb_addr = Signal(self.addr_layout)
                m.d.comb += [
                    wb_addr.offset.eq(0),
                    wb_addr.index.eq(flush_index),
                    wb_addr.tag.eq(self.mem.tag_rd_data[dirty_way].tag),
                ]
                self.refiller.start_writeback(m, addr=self.serialize_addr(wb_addr))
                m.d.sync += [
                    wb_way.eq(dirty_way),
                    wb_index.eq(flush_index),
                    wb_word_counter.eq(0),
                    wb_triggered_by_flush.eq(1),
                    flush_writeback_pending.eq(1),
                ]
            with m.Else():
                # No dirty ways — invalidate all ways at this set
                m.d.comb += [
                    self.mem.way_wr_en.eq(C(1).replicate(self.params.num_of_ways)),
                    self.mem.tag_wr_index.eq(flush_index),
                    self.mem.tag_wr_data.valid.eq(0),
                    self.mem.tag_wr_data.dirty.eq(0),
                    self.mem.tag_wr_data.tag.eq(0),
                    self.mem.tag_wr_en.eq(1),
                ]

                with m.If(flush_index == self.params.num_of_sets - 1):
                    m.d.comb += flush_finish.eq(1)
                with m.Else():
                    m.d.sync += flush_index.eq(flush_index + 1)
                    m.d.sync += flush_data_valid.eq(0)

        # ------------------ WRITEBACK ---

        with m.If(fsm.ongoing("WRITEBACK")):
            word_bytes_log = exact_log2(self.params.word_width_bytes)
            m.d.comb += [
                self.mem.data_rd_addr.index.eq(wb_index),
                self.mem.data_rd_addr.offset.eq(wb_word_counter << word_bytes_log),
            ]

        @def_method(m, self.provide_writeback_data, ready=fsm.ongoing("WRITEBACK"))
        def _():
            m.d.sync += wb_word_counter.eq(wb_word_counter + 1)
            return {"data": self.mem.data_rd_data[wb_way]}

        # End the writeback
        # Runs if FSM is WRITEBACK and refiller.accept_writeback is ready
        with Transaction(name="WritebackEnd").body(m, ready=fsm.ongoing("WRITEBACK")):
            result = self.refiller.accept_writeback(m)
            self.perf_errors.incr(m, enable_call=result.error)

            with m.If(~result.error):
                # After a successful writeback, the victim line can be invalidated.
                m.d.comb += [
                    self.mem.way_wr_en.eq(1 << wb_way),
                    self.mem.tag_wr_index.eq(wb_index),
                    self.mem.tag_wr_data.valid.eq(0),
                    self.mem.tag_wr_data.dirty.eq(0),
                    self.mem.tag_wr_data.tag.eq(0),
                    self.mem.tag_wr_en.eq(1),
                ]

                with m.If(wb_triggered_by_flush):
                    m.d.comb += writeback_done_flush.eq(1)
                with m.Else():
                    self.refiller.start_refill(m, addr=self.serialize_addr(refill_addr))
                    m.d.comb += writeback_done_refill.eq(1)

            with m.Else():
                m.d.comb += writeback_done_error.eq(1)
                with m.If(~wb_triggered_by_flush):
                    m.d.sync += [
                        res_reg.data.eq(0),
                        res_reg.error.eq(1),
                        res_valid.eq(1),
                        pending_req_valid.eq(0),
                        lookup_valid.eq(0),
                        rr_used.eq(0),
                    ]

        # Writeback is started either by lookup or flush

        # ---------- LOOKUP ----

        with Transaction(name="Lookup").body(m, ready=fsm.ongoing("LOOKUP") & pending_req_valid & lookup_valid):
            # If cache hit: set dirty bit if store -> return data
            # If cache miss: if victim has dirty bit, writeback cache line -> refill -> return data
            tag_hit = Array(
                self.mem.tag_rd_data[i].valid & (self.mem.tag_rd_data[i].tag == lookup_addr.tag)
                for i in range(self.params.num_of_ways)
            )

            tag_hit_any = Signal()
            m.d.comb += tag_hit_any.eq(Cat(tag_hit).any())

            hit_way = Signal(range(self.params.num_of_ways))
            load_data = Signal(self.params.word_width)

            # TODO: optimize that
            for i in range(self.params.num_of_ways):
                with m.If(tag_hit[i]):
                    m.d.comb += [
                        hit_way.eq(i),
                        load_data.eq(self.mem.data_rd_data[i]),
                    ]

            with m.If(tag_hit_any):
                with m.If(pending_req.store):
                    m.d.comb += [
                        self.mem.way_wr_en.eq(1 << hit_way),
                        self.mem.data_wr_en.eq(1),
                        self.mem.data_wr_addr.index.eq(lookup_addr.index),
                        self.mem.data_wr_addr.offset.eq(lookup_addr.offset),
                        self.mem.data_wr_data.eq(pending_req.data),
                        self.mem.data_wr_mask.eq(pending_req.byte_mask),
                        self.mem.tag_wr_index.eq(lookup_addr.index),
                        self.mem.tag_wr_data.valid.eq(1),
                        self.mem.tag_wr_data.dirty.eq(1),
                        self.mem.tag_wr_data.tag.eq(lookup_addr.tag),
                        self.mem.tag_wr_en.eq(1),
                    ]
                    m.d.sync += [
                        res_reg.data.eq(0),
                        res_reg.error.eq(0),
                    ]
                with m.Else():
                    m.d.sync += [
                        res_reg.data.eq(load_data),
                        res_reg.error.eq(0),
                    ]

                m.d.sync += [
                    pending_req_valid.eq(0),
                    lookup_valid.eq(0),
                    res_valid.eq(1),
                ]

            with m.Else():
                # we check if dirty, if yes, change FSM to writeback
                # then, we refill
                # then, lookup transaction starts again, now with proper refilled cache line

                # 1. Choose way determined by round-robin
                victim_way = Signal(range(self.params.num_of_ways))
                victim_used_rr = Signal()
                m.d.comb += [victim_way.eq(rr_way), victim_used_rr.eq(1)]

                # 2. If there are already some invalid ways, use theam instead of round-robin
                for i in reversed(range(self.params.num_of_ways)):
                    with m.If(~self.mem.tag_rd_data[i].valid):
                        m.d.comb += [victim_way.eq(i), victim_used_rr.eq(0)]

                m.d.sync += [rr_used.eq(victim_used_rr)]

                victim_tag_data = self.mem.tag_rd_data[victim_way]
                victim_addr = Signal(self.addr_layout)
                m.d.comb += [
                    victim_addr.offset.eq(0),
                    victim_addr.index.eq(lookup_addr.index),
                    victim_addr.tag.eq(victim_tag_data.tag),
                ]

                aligned_refill_addr = self.serialize_addr(lookup_addr) & ~((1 << self.params.offset_bits) - 1)

                with m.If(victim_tag_data.valid & victim_tag_data.dirty):
                    # Writeback, then Refill
                    self.refiller.start_writeback(m, addr=self.serialize_addr(victim_addr))
                    m.d.comb += needs_writeback.eq(1)
                    m.d.sync += [
                        wb_way.eq(victim_way),
                        wb_index.eq(lookup_addr.index),
                        wb_word_counter.eq(0),
                        wb_triggered_by_flush.eq(0),
                        refill_addr.offset.eq(0),
                        refill_addr.index.eq(lookup_addr.index),
                        refill_addr.tag.eq(lookup_addr.tag),
                        refill_way.eq(victim_way),
                        refill_error.eq(0),
                        lookup_valid.eq(0),
                    ]
                with m.Else():
                    # Refill
                    self.refiller.start_refill(m, aligned_refill_addr)
                    m.d.comb += needs_refill.eq(1)
                    m.d.sync += [
                        refill_addr.offset.eq(0),
                        refill_addr.index.eq(lookup_addr.index),
                        refill_addr.tag.eq(lookup_addr.tag),
                        refill_way.eq(victim_way),
                        refill_error.eq(0),
                        lookup_valid.eq(0),
                    ]

        # ------------- REFILL ---------
        with Transaction(name="Refill").body(m, ready=fsm.ongoing("REFILL")):
            ret = self.refiller.accept_refill(m)
            deserialized = self.deserialize_addr(ret.addr)
            refill_error_now = Signal()
            m.d.comb += refill_error_now.eq(refill_error | ret.error)

            with m.If(~ret.error):
                m.d.comb += [
                    self.mem.way_wr_en.eq(1 << refill_way),
                    self.mem.data_wr_en.eq(1),
                    self.mem.data_wr_addr.index.eq(deserialized["index"]),
                    self.mem.data_wr_addr.offset.eq(deserialized["offset"]),
                    self.mem.data_wr_data.eq(ret.data),
                    self.mem.data_wr_mask.eq((1 << self.params.word_width_bytes) - 1),
                ]

            with m.If(ret.error):
                m.d.sync += refill_error.eq(1)

            with m.If(ret.last):
                m.d.comb += refill_finish.eq(1)
                with m.If(~refill_error_now):
                    m.d.comb += [
                        self.mem.way_wr_en.eq(1 << refill_way),
                        self.mem.tag_wr_index.eq(refill_addr.index),
                        self.mem.tag_wr_data.valid.eq(1),
                        self.mem.tag_wr_data.dirty.eq(0),
                        self.mem.tag_wr_data.tag.eq(refill_addr.tag),
                        self.mem.tag_wr_en.eq(1),
                    ]
                    m.d.sync += [
                        lookup_valid.eq(0),
                        refill_error.eq(0),
                        rr_used.eq(0),
                    ]
                    # move
                    with m.If(rr_used):
                        m.d.sync += [
                            rr_way.eq(Mux(refill_way == self.params.num_of_ways - 1, 0, refill_way + 1)),
                        ]

                with m.Else():
                    m.d.sync += [
                        res_reg.data.eq(0),
                        res_reg.error.eq(1),
                        res_valid.eq(1),
                        pending_req_valid.eq(0),
                        lookup_valid.eq(0),
                        refill_error.eq(0),
                        rr_used.eq(0),
                    ]

        # ------ Methods ---
        @def_method(m, self.accept_res, ready=res_valid)
        def _():
            m.d.sync += res_valid.eq(0)
            return res_reg

        @def_method(
            m,
            self.issue_req,
            ready=fsm.ongoing("LOOKUP") & ~pending_req_valid & ~lookup_valid & ~res_valid,
        )
        def _(addr: Value, data: Value, byte_mask: Value, store: Value):
            deserialized = self.deserialize_addr(addr)

            with m.If(store):
                self.perf_stores.incr(m)
            with m.Else():
                self.perf_loads.incr(m)

            m.d.sync += [
                pending_req.addr.eq(addr),
                pending_req.data.eq(data),
                pending_req.byte_mask.eq(byte_mask),
                pending_req.store.eq(store),
                pending_req_valid.eq(1),
                assign(lookup_addr, deserialized),
                lookup_valid.eq(0),
            ]

        # Connection to memory
        with m.If(fsm.ongoing("FLUSH")):
            m.d.comb += self.mem.tag_rd_index.eq(flush_index)
        with m.Elif(fsm.ongoing("WRITEBACK")):
            m.d.comb += [
                self.mem.data_rd_addr.index.eq(wb_index),
                self.mem.data_rd_addr.offset.eq(wb_word_counter << exact_log2(self.params.word_width_bytes)),
            ]
        with m.Else():
            m.d.comb += [
                self.mem.tag_rd_index.eq(lookup_addr.index),
                self.mem.data_rd_addr.index.eq(lookup_addr.index),
                self.mem.data_rd_addr.offset.eq(lookup_addr.offset),
            ]

        return m


class DCacheMemory(Elaboratable):
    """A helper module for managing memories used in the data cache.

    Extends the ICache memory design with:
    - A dirty bit in the tag array (for write-back policy).
    - Byte-granularity write enables on the data array (for sb/sh/sw).
    """

    def __init__(self, params: DCacheParameters) -> None:
        self.params = params

        # Dirty bit - if set, it means cache was modified since loading from ram; we need to save the cache on flush
        self.tag_data_layout = make_layout(("valid", 1), ("dirty", 1), ("tag", self.params.tag_bits))

        self.way_wr_en = Signal(self.params.num_of_ways)

        self.tag_rd_index = Signal(self.params.index_bits)
        self.tag_rd_data = Array([Signal(self.tag_data_layout) for _ in range(self.params.num_of_ways)])
        self.tag_wr_index = Signal(self.params.index_bits)
        self.tag_wr_en = Signal()
        self.tag_wr_data = Signal(self.tag_data_layout)

        self.data_addr_layout = make_layout(("index", self.params.index_bits), ("offset", self.params.offset_bits))

        self.word_bits = params.word_width
        self.word_bytes = params.word_width // 8

        self.data_rd_addr = Signal(self.data_addr_layout)
        self.data_rd_data = Array([Signal(self.word_bits) for _ in range(self.params.num_of_ways)])

        self.data_wr_addr = Signal(self.data_addr_layout)
        self.data_wr_en = Signal()
        self.data_wr_data = Signal(self.word_bits)

        self.data_wr_mask = Signal(self.word_bytes)  # byte-granularity write mask
        self.tag_mems: list[memory.Memory] = []
        self.data_mems: list[memory.Memory] = []

    def elaborate(self, platform):
        m = TModule()

        for i in range(self.params.num_of_ways):
            way_wr = self.way_wr_en[i]

            tag_mem = memory.Memory(shape=self.tag_data_layout, depth=self.params.num_of_sets, init=[])
            self.tag_mems.append(tag_mem)

            tag_mem_wp = tag_mem.write_port()
            tag_mem_rp = tag_mem.read_port(transparent_for=[tag_mem_wp])
            m.submodules[f"tag_mem_{i}"] = tag_mem

            m.d.comb += [
                assign(self.tag_rd_data[i], tag_mem_rp.data),
                tag_mem_rp.addr.eq(self.tag_rd_index),
                tag_mem_wp.addr.eq(self.tag_wr_index),
                assign(tag_mem_wp.data, self.tag_wr_data),
                tag_mem_wp.en.eq(self.tag_wr_en & way_wr),
            ]

            data_mem = memory.Memory(
                shape=self.word_bits,
                depth=self.params.num_of_sets * self.params.words_in_line,
                init=[],
            )
            self.data_mems.append(data_mem)
            data_mem_wp = data_mem.write_port(granularity=8)
            data_mem_rp = data_mem.read_port(transparent_for=[data_mem_wp])
            m.submodules[f"data_mem_{i}"] = data_mem

            word_bytes_log = exact_log2(self.word_bytes)
            rd_addr = Cat(self.data_rd_addr.offset, self.data_rd_addr.index)[word_bytes_log:]
            wr_addr = Cat(self.data_wr_addr.offset, self.data_wr_addr.index)[word_bytes_log:]

            m.d.comb += [
                self.data_rd_data[i].eq(data_mem_rp.data),
                data_mem_rp.addr.eq(rd_addr),
                data_mem_wp.addr.eq(wr_addr),
                Value.cast(data_mem_wp.data).eq(self.data_wr_data),
                data_mem_wp.en.eq(Mux(self.data_wr_en & way_wr, self.data_wr_mask, 0)),
            ]

        return m
