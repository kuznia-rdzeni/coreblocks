from functools import reduce
import operator

from amaranth import *
from amaranth.utils import log2_int

from transactron.core import def_method, Priority, TModule
from transactron import Method, Transaction
from coreblocks.params import ICacheLayouts, ICacheParameters
from transactron.utils import assign, OneHotSwitchDynamic
from transactron.lib import *
from coreblocks.peripherals.wishbone import WishboneMaster

from coreblocks.cache.iface import CacheInterface, CacheRefillerInterface

__all__ = [
    "ICache",
    "ICacheBypass",
]


def extract_instr_from_word(m: TModule, params: ICacheParameters, word: Signal, addr: Value):
    instr_out = Signal(params.instr_width)
    if len(word) == 32:
        m.d.comb += instr_out.eq(word)
    elif len(word) == 64:
        with m.If(addr[2] == 0):
            m.d.comb += instr_out.eq(word[:32])  # Take lower 4 bytes
        with m.Else():
            m.d.comb += instr_out.eq(word[32:])  # Take upper 4 bytes
    else:
        raise RuntimeError("Word size different than 32 and 64 is not supported")
    return instr_out


class ICacheBypass(Elaboratable, CacheInterface):
    def __init__(self, layouts: ICacheLayouts, params: ICacheParameters, wb_master: WishboneMaster) -> None:
        self.params = params
        self.wb_master = wb_master

        self.issue_req = Method(i=layouts.issue_req)
        self.accept_res = Method(o=layouts.accept_res)
        self.flush = Method()

    def elaborate(self, platform):
        m = TModule()

        req_addr = Signal(self.params.addr_width)

        @def_method(m, self.issue_req)
        def _(addr: Value) -> None:
            m.d.sync += req_addr.eq(addr)
            self.wb_master.request(
                m,
                addr=addr >> log2_int(self.params.word_width_bytes),
                data=0,
                we=0,
                sel=C(1).replicate(self.wb_master.wb_params.data_width // self.wb_master.wb_params.granularity),
            )

        @def_method(m, self.accept_res)
        def _():
            res = self.wb_master.result(m)
            return {
                "instr": extract_instr_from_word(m, self.params, res.data, req_addr),
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
    `refiller_accept` should be ready to be called whenever the refiller has another word ready
    to be written to cache. `refiller_accept` should set `last` bit when either an error occurs
    or the transfer is over. After issuing `last` bit, `refiller_accept` shouldn't be ready until
    the next transfer is started.
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

        self.addr_layout = [
            ("offset", self.params.offset_bits),
            ("index", self.params.index_bits),
            ("tag", self.params.tag_bits),
        ]

    def deserialize_addr(self, raw_addr: Value) -> dict[str, Value]:
        return {
            "offset": raw_addr[: self.params.offset_bits],
            "index": raw_addr[self.params.index_start_bit : self.params.index_end_bit + 1],
            "tag": raw_addr[-self.params.tag_bits :],
        }

    def serialize_addr(self, addr: Record) -> Value:
        return Cat(addr.offset, addr.index, addr.tag)

    def elaborate(self, platform):
        m = TModule()

        m.submodules.mem = self.mem = ICacheMemory(self.params)
        m.submodules.req_fifo = self.req_fifo = FIFO(layout=self.addr_layout, depth=2)
        m.submodules.res_fwd = self.res_fwd = Forwarder(layout=self.layouts.accept_res)

        # State machine logic
        needs_refill = Signal()
        refill_finish = Signal()
        refill_error = Signal()

        flush_start = Signal()
        flush_finish = Signal()

        with m.FSM(reset="FLUSH") as fsm:
            with m.State("FLUSH"):
                with m.If(flush_finish):
                    m.next = "LOOKUP"

            with m.State("LOOKUP"):
                with m.If(needs_refill):
                    m.next = "REFILL"
                with m.Elif(flush_start):
                    m.next = "FLUSH"

            with m.State("REFILL"):
                with m.If(refill_finish):
                    m.next = "LOOKUP"

        accepting_requests = fsm.ongoing("LOOKUP") & ~needs_refill

        # Replacement policy
        way_selector = Signal(self.params.num_of_ways, reset=1)
        with m.If(refill_finish):
            m.d.sync += way_selector.eq(way_selector.rotate_left(1))

        # Fast path - read requests
        request_valid = self.req_fifo.read.ready
        request_addr = Record(self.addr_layout)

        tag_hit = [tag_data.valid & (tag_data.tag == request_addr.tag) for tag_data in self.mem.tag_rd_data]
        tag_hit_any = reduce(operator.or_, tag_hit)

        mem_out = Signal(self.params.word_width)
        for i in OneHotSwitchDynamic(m, Cat(tag_hit)):
            m.d.comb += mem_out.eq(self.mem.data_rd_data[i])

        instr_out = extract_instr_from_word(m, self.params, mem_out, request_addr[:])

        refill_error_saved = Signal()
        m.d.comb += needs_refill.eq(request_valid & ~tag_hit_any & ~refill_error_saved)

        with Transaction().body(m, request=request_valid & fsm.ongoing("LOOKUP") & (tag_hit_any | refill_error_saved)):
            self.res_fwd.write(m, instr=instr_out, error=refill_error_saved)
            m.d.sync += refill_error_saved.eq(0)

        @def_method(m, self.accept_res)
        def _():
            self.req_fifo.read(m)
            return self.res_fwd.read(m)

        mem_read_addr = Record(self.addr_layout)
        m.d.comb += assign(mem_read_addr, request_addr)

        @def_method(m, self.issue_req, ready=accepting_requests)
        def _(addr: Value) -> None:
            deserialized = self.deserialize_addr(addr)
            # Forward read address only if the method is called
            m.d.comb += assign(mem_read_addr, deserialized)
            m.d.sync += assign(request_addr, deserialized)

            self.req_fifo.write(m, deserialized)

        m.d.comb += [
            self.mem.tag_rd_index.eq(mem_read_addr.index),
            self.mem.data_rd_addr.index.eq(mem_read_addr.index),
            self.mem.data_rd_addr.offset.eq(mem_read_addr.offset),
        ]

        # Flush logic
        flush_index = Signal(self.params.index_bits)
        with m.If(fsm.ongoing("FLUSH")):
            m.d.sync += flush_index.eq(flush_index + 1)

        @def_method(m, self.flush, ready=accepting_requests)
        def _() -> None:
            m.d.sync += flush_index.eq(0)
            m.d.comb += flush_start.eq(1)

        m.d.comb += flush_finish.eq(flush_index == self.params.num_of_sets - 1)

        # Slow path - data refilling
        with Transaction().body(m, request=fsm.ongoing("LOOKUP") & needs_refill):
            # Align to the beginning of the cache line
            aligned_addr = self.serialize_addr(request_addr) & ~((1 << self.params.offset_bits) - 1)
            self.refiller.start_refill(m, addr=aligned_addr)

        with Transaction().body(m):
            ret = self.refiller.accept_refill(m)
            deserialized = self.deserialize_addr(ret.addr)

            m.d.top_comb += [
                self.mem.data_wr_addr.index.eq(deserialized["index"]),
                self.mem.data_wr_addr.offset.eq(deserialized["offset"]),
                self.mem.data_wr_data.eq(ret.data),
            ]

            m.d.comb += self.mem.data_wr_en.eq(1)
            m.d.comb += refill_finish.eq(ret.last)
            m.d.comb += refill_error.eq(ret.error)
            m.d.sync += refill_error_saved.eq(ret.error)

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
                self.mem.tag_wr_index.eq(request_addr.index),
                self.mem.tag_wr_data.valid.eq(~refill_error),
                self.mem.tag_wr_data.tag.eq(request_addr.tag),
                self.mem.tag_wr_en.eq(refill_finish),
            ]

        return m


class ICacheMemory(Elaboratable):
    """A helper module for managing memories used in the instruction cache.

    In case of an associative cache, all address and write data lines are shared.
    Writes are multiplexed using one-hot `way_wr_en` signal. Read data lines from all
    ways are separately exposed (as an array).

    The data memory is addressed using a machine word.
    """

    def __init__(self, params: ICacheParameters) -> None:
        self.params = params

        self.tag_data_layout = [("valid", 1), ("tag", self.params.tag_bits)]

        self.way_wr_en = Signal(self.params.num_of_ways)

        self.tag_rd_index = Signal(self.params.index_bits)
        self.tag_rd_data = Array([Record(self.tag_data_layout) for _ in range(self.params.num_of_ways)])
        self.tag_wr_index = Signal(self.params.index_bits)
        self.tag_wr_en = Signal()
        self.tag_wr_data = Record(self.tag_data_layout)

        self.data_addr_layout = [("index", self.params.index_bits), ("offset", self.params.offset_bits)]

        self.data_rd_addr = Record(self.data_addr_layout)
        self.data_rd_data = Array([Signal(self.params.word_width) for _ in range(self.params.num_of_ways)])
        self.data_wr_addr = Record(self.data_addr_layout)
        self.data_wr_en = Signal()
        self.data_wr_data = Signal(self.params.word_width)

    def elaborate(self, platform):
        m = TModule()

        for i in range(self.params.num_of_ways):
            way_wr = self.way_wr_en[i]

            tag_mem = Memory(width=len(self.tag_wr_data), depth=self.params.num_of_sets)
            tag_mem_rp = tag_mem.read_port()
            tag_mem_wp = tag_mem.write_port()
            m.submodules[f"tag_mem_{i}_rp"] = tag_mem_rp
            m.submodules[f"tag_mem_{i}_wp"] = tag_mem_wp

            m.d.comb += [
                assign(self.tag_rd_data[i], tag_mem_rp.data),
                tag_mem_rp.addr.eq(self.tag_rd_index),
                tag_mem_wp.addr.eq(self.tag_wr_index),
                assign(tag_mem_wp.data, self.tag_wr_data),
                tag_mem_wp.en.eq(self.tag_wr_en & way_wr),
            ]

            data_mem = Memory(width=self.params.word_width, depth=self.params.num_of_sets * self.params.words_in_block)
            data_mem_rp = data_mem.read_port()
            data_mem_wp = data_mem.write_port()
            m.submodules[f"data_mem_{i}_rp"] = data_mem_rp
            m.submodules[f"data_mem_{i}_wp"] = data_mem_wp

            # We address the data RAM using machine words, so we have to
            # discard a few least significant bits from the address.
            redundant_offset_bits = log2_int(self.params.word_width_bytes)
            rd_addr = Cat(self.data_rd_addr.offset, self.data_rd_addr.index)[redundant_offset_bits:]
            wr_addr = Cat(self.data_wr_addr.offset, self.data_wr_addr.index)[redundant_offset_bits:]

            m.d.comb += [
                self.data_rd_data[i].eq(data_mem_rp.data),
                data_mem_rp.addr.eq(rd_addr),
                data_mem_wp.addr.eq(wr_addr),
                data_mem_wp.data.eq(self.data_wr_data),
                data_mem_wp.en.eq(self.data_wr_en & way_wr),
            ]

        return m
      