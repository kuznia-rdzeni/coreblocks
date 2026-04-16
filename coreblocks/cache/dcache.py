from amaranth import *
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

        flush_start = Signal()
        flush_finish = Signal()
        needs_writeback = Signal() # if we missed and victim is dirty, writeback the victim and load new line
        needs_refill = Signal()
        refill_finish = Signal()
        writeback_finish = Signal()

        wb_way = Signal(range(self.params.num_of_ways))
        wb_index = Signal(self.params.index_bits)
        wb_word_counter = Signal(range(self.params.words_in_line))

        wb_triggered_by_flush = Signal()

        with m.FSM(init="FLUSH") as fsm:
            with m.State("FLUSH"):
                with m.If(flush_finish):
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
                """
                Writeback does:
                1. Gets dirty line data from memory
                2. Iterates through every word in dirty line
                    1. Send that to refiller -- refiller calls provide_writebackdata
                3. Accept the writeback (call refiller.accept_writeback)
                """
                # transactions with handle state change, fix that later
                # with m.If(writeback_finish):
                #     with m.If(wb_triggered_by_flush):
                #         m.d.sync += wb_triggered_by_flush.eq(0)
                #         m.next = "FLUSH"
                #     with m.Else():
                #         m.next = "REFILL"


        # ------------- FLUSH -------
        flush_index = Signal(self.params.index_bits) # Index of cache line that is gonna be writen back
        m.d.comb += flush_finish.eq(flush_index == self.params.num_of_sets - 1) # if is last, then next cycle we finish

        @def_method(m, self.flush)
        def _():
            log.info(m, True, "Flushing the cache...")
            m.d.sync += flush_index.eq(0)
            m.d.comb += flush_start.eq(1)

        # TODO: Flush Transaction — iterate sets/ways, check dirty, start_writeback or invalidate
        with Transaction(name="Flush").body(m, ready=fsm.ongoing("FLUSH")):
            # tag_rd_data is ready from previous cycle (tag_rd_index was set to flush_index)
            # TODO: check dirty per way, start_writeback if dirty, invalidate if clean, advance flush_index
            pass


        # Connect tag_rd_index to flush_index when in FLUSH state, so SRAM reads tags
        with m.If(fsm.ongoing("FLUSH")):
            m.d.comb += self.mem.tag_rd_index.eq(flush_index)

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
            # TODO: handle error
            with m.If(~wb_triggered_by_flush):
                pass # todo: start refill
            with m.Else():
                m.next = "FLUSH"
            m.d.comb += writeback_finish.eq(1)


        # Writeback is started either by lookup or flush


        # ---------- LOOKUP ----

        with Transaction(name="Lookup").body(m, ready=fsm.ongoing("LOOKUP")):

            # TODO
            tag_hit_any = Signal()

            with m.If(~tag_hit_any):

                victim_dirty = Signal()
                # TODO

                with m.If(victim_dirty):
                    self.refiller.start_writeback(m, addr=0) #todo
                    m.d.sync += wb_way.eq(1) #todo
                    m.d.sync += wb_index.eq(1) #todo
                    m.d.sync += wb_word_counter.eq(0)
                    m.d.sync += wb_triggered_by_flush.eq(0)
                    m.next = "WRITEBACK"
                with m.Else():
                    self.refiller.start_refill(m, addr=0) #todo
                    m.next = "REFILL"

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

    def elaborate(self, platform):
        m = TModule()

        for i in range(self.params.num_of_ways):
            way_wr = self.way_wr_en[i]

            tag_mem = memory.Memory(shape=self.tag_data_layout, depth=self.params.num_of_sets, init=[])

            tag_mem_wp = tag_mem.write_port()
            tag_mem_rp = tag_mem.read_port(transparent_for=[tag_mem_wp])
            m.submodules[f"tag_mem_{i}"] = tag_mem

            m.d.comb += [
                assign(self.tag_rd_data[i], tag_mem_rp.data),  # odczytuje dane z tagu dla kazdego way
                tag_mem_rp.addr.eq(self.tag_rd_index),  # ustawia adres ktory tag odczytujemy
                tag_mem_wp.addr.eq(self.tag_wr_index),  # ustawia adres do ktorego piszemy
                assign(tag_mem_wp.data, self.tag_wr_data),  # podlacza dane ktore chcemy zapisac
                tag_mem_wp.en.eq(self.tag_wr_en & way_wr),  # zapis wykona sie jesli to jest 1
            ]

            data_mem = memory.Memory(
                shape=self.word_bits,
                depth=self.params.num_of_sets * self.params.words_in_line,
                init=[],
            )
            data_mem_wp = data_mem.write_port(
                granularity=8
            )  # 1 byte granularity, 1 bit maski data_wr_mask odpowiada 1 bajtowi danych
            data_mem_rp = data_mem.read_port(transparent_for=[data_mem_wp])
            m.submodules[f"data_mem_{i}"] = data_mem

            rd_addr = Cat(self.data_rd_addr.offset, self.data_rd_addr.index)[exact_log2(self.word_bytes)]
            wr_addr = Cat(self.data_wr_addr.offset, self.data_wr_addr.index)[exact_log2(self.word_bytes)]

            m.d.comb += [
                self.data_rd_data[i].eq(data_mem_rp.data),  # podlaczamy dane ktore chcemy odczytac na wyjscie z klasy
                data_mem_rp.addr.eq(rd_addr),  # adres wyliczony z offset+idx
                data_mem_wp.addr.eq(wr_addr),  # adres wyliczony z offset+idx
                data_mem_wp.data.eq(self.data_wr_data),  # podlaczamy dane ktore chcemy zapisac na wejscie do srodka
                # dany bit odpowiada czy zapisujemy dany bajt czy ignorujemy
                data_mem_wp.en.eq(Mux(self.data_wr_en & way_wr, self.data_wr_mask, 0)),
            ]

        return m
