from functools import reduce
import operator

from amaranth import *
from amaranth.utils import log2_int

from coreblocks.transactions.core import def_method
from coreblocks.transactions import Method, Transaction
from coreblocks.params import GenParams, ICacheLayouts
from coreblocks.utils import assign
from coreblocks.transactions.lib import *
from coreblocks.peripherals.wishbone import WishboneMaster


__all__ = ["ICacheParameters", "ICache", "SimpleWBCacheRefiller"]


class ICacheParameters:
    """Parameters of the Instruction Cache.

    Parameters
    ----------
    addr_width : int
        Length of addresses used in the cache (in bits).
    num_of_ways : int
        Associativity of the cache. Defaults to 2 ways.
    num_of_sets : int
        Number of cache sets. Defaults to 128 sets.
    block_size_bytes : int
        The size of a single cache block in bytes. Defaults to 32 bytes.
    """

    def __init__(self, *, addr_width, num_of_ways=2, num_of_sets=128, block_size_bytes=32):
        self.addr_width = addr_width
        self.num_of_ways = num_of_ways
        self.num_of_sets = num_of_sets
        self.block_size_bytes = block_size_bytes

        def is_power_of_two(n):
            return (n != 0) and (n & (n - 1) == 0)

        if self.num_of_ways not in {1, 2, 4, 8}:
            raise ValueError(f"num_of_ways must be 1, 2, 4 or 8, not {num_of_ways}")
        if not is_power_of_two(num_of_sets):
            raise ValueError(f"num_of_sets must be a power of 2, not {num_of_sets}")
        if not is_power_of_two(block_size_bytes) or block_size_bytes < 4:
            raise ValueError(f"block_size_bytes must be a power of 2 and not smaller than 4, not {block_size_bytes}")

        self.offset_bits = log2_int(self.block_size_bytes)
        self.index_bits = log2_int(self.num_of_sets)
        self.tag_bits = self.addr_width - self.offset_bits - self.index_bits

        self.index_start_bit = self.offset_bits
        self.index_end_bit = self.offset_bits + self.index_bits - 1


class ICache(Elaboratable):
    """A simple set-associative instruction cache.

    There are two methods exposed by this module, which are meant to be used
    by the cache user: `issue_req`, `accept_res`.

    A few notes about the cache:
        1) The replacement policy is a pseudo random scheme. Every time a line is trashed,
        we select the next way we write to (we keep one global counter for selecting the next way).

        2) The latency during a cache hit is exactly one cycle.

        3) Information about fetch errors is not cached. That is, if an error happens during
        line refill, next access in that line, will retrigger a refill (which most likely
        will return an error again).


    Refilling a cache line is abstracted away from this module. ICache module needs two methods
    from the refiller `refiller_start`, which is called whenever we need to refill a cache line.
    `refiller_accept` should be ready to be called whenever the refiller has another word ready
    to be written to cache. `refiller_accept` should set `last` bit when either an error occurs
    or the transfer is over. After issuing `last` bit, `refiller_accept` shouldn't be ready until
    the next transfer is started.


    Attributes
    ----------
    issue_req : Method
        A method that is used to issue a cache lookup request.
    accept_res : ICacheParameters
        A method that is used to accept the result of a cache lookup request.
    """

    def __init__(
        self, gen_params: GenParams, cache_params: ICacheParameters, refiller_start: Method, refiller_accept: Method
    ) -> None:
        """
        Parameters
        ----------
        gen_params : GenParams
            Instance of GenParams with parameters which should be used to generate
            the cache.
        cache_params : ICacheParameters
            Instance of ICacheParameters.
        refiller_start : Method
            A method with input layout ICacheLayouts::start_refill
        refiller_accept : Method
            A method with output layout ICacheLayouts::accept_refill
        """
        self.gp = gen_params
        self.params = cache_params

        if self.params.block_size_bytes % (self.gp.isa.xlen // 8) != 0:
            raise ValueError("block_size_bytes must be divisble by the machine word size")

        self.refiller_start = refiller_start
        self.refiller_accept = refiller_accept

        layouts = self.gp.get(ICacheLayouts)
        self.issue_req = Method(i=layouts.issue_req)
        self.accept_res = Method(o=layouts.accept_res)

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

    def elaborate(self, platform) -> Module:
        m = Module()

        m.submodules.mem = self.mem = ICacheMemory(self.gp, self.params)
        m.submodules.req_fifo = self.req_fifo = FIFO(layout=self.addr_layout, depth=2)
        m.submodules.res_fwd = self.res_fwd = Forwarder(layout=self.gp.get(ICacheLayouts).accept_res)

        # State machine logic
        needs_refill = Signal()
        refill_finish = Signal()
        refill_error = Signal()

        with m.FSM() as fsm:
            with m.State("LOOKUP"):
                with m.If(needs_refill):
                    m.next = "REFILL"

            with m.State("REFILL"):
                with m.If(refill_finish):
                    m.next = "LOOKUP"

        # Replacement policy
        way_selector = Signal(log2_int(self.params.num_of_ways))
        m.d.comb += self.mem.way_wr_sel.eq(way_selector)
        with m.If(refill_finish):
            m.d.sync += way_selector.eq(way_selector + 1)

        # Fast path - read requests
        request_valid = self.req_fifo.read.ready
        request_addr = Record(self.addr_layout)

        tag_hit = [tag_data.valid & (tag_data.tag == request_addr.tag) for tag_data in self.mem.tag_rd_data]
        tag_hit_any = reduce(operator.or_, tag_hit)

        instr_out = Signal(self.gp.isa.ilen)
        for i in range(self.params.num_of_ways):
            with m.If(tag_hit[i]):
                m.d.comb += instr_out.eq(self.mem.data_rd_data[i])  # TODO(jurb): this won't work on rv64

        refill_error_d = Signal()
        m.d.sync += refill_error_d.eq(refill_error)
        m.d.comb += needs_refill.eq(request_valid & ~tag_hit_any & ~refill_error_d)

        with Transaction().body(m, request=request_valid & fsm.ongoing("LOOKUP") & (tag_hit_any | refill_error_d)):
            self.res_fwd.write(m, instr=instr_out, error=refill_error_d)

        @def_method(m, self.accept_res)
        def _():
            self.req_fifo.read(m)
            return self.res_fwd.read(m)

        mem_read_addr = Record(self.addr_layout)
        m.d.comb += assign(mem_read_addr, request_addr)

        @def_method(m, self.issue_req, ready=fsm.ongoing("LOOKUP") & ~needs_refill)
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

        # Slow path - data refilling
        m.d.comb += [
            self.mem.tag_wr_index.eq(request_addr.index),
            self.mem.tag_wr_data.valid.eq(~refill_error),
            self.mem.tag_wr_data.tag.eq(request_addr.tag),
            self.mem.tag_wr_en.eq(refill_finish),
        ]

        with Transaction().body(m, request=fsm.ongoing("LOOKUP") & needs_refill):
            # Align to the beginning of the cache line
            aligned_addr = self.serialize_addr(request_addr) & ~((1 << self.params.offset_bits) - 1)
            self.refiller_start(m, addr=aligned_addr)

        with Transaction().body(m):
            ret = self.refiller_accept(m)
            deserialized = self.deserialize_addr(ret.addr)

            Transaction.comb += [
                self.mem.data_wr_addr.index.eq(deserialized["index"]),
                self.mem.data_wr_addr.offset.eq(deserialized["offset"]),
                self.mem.data_wr_data.eq(ret.data),
            ]

            m.d.comb += self.mem.data_wr_en.eq(1)
            m.d.comb += refill_finish.eq(ret.last)
            m.d.comb += refill_error.eq(ret.error)

        return m


class ICacheMemory(Elaboratable):
    """A helper module for managing memories used in the instruction cache.

    In case of an associative cache, all address and write data lines are shared.
    Writes are multiplexed using the `way_wr_sel` signal. Read data lines from all
    ways are separately exposed (as an array).

    The data memory is addressed using a machine word.
    """

    def __init__(self, gen_params: GenParams, cache_params: ICacheParameters) -> None:
        self.gp = gen_params
        self.params = cache_params

        self.tag_data_layout = [("valid", 1), ("tag", self.params.tag_bits)]

        self.way_wr_sel = Signal(log2_int(self.params.num_of_ways))

        self.tag_rd_index = Signal(self.params.index_bits)
        self.tag_rd_data = Array([Record(self.tag_data_layout) for _ in range(self.params.num_of_ways)])
        self.tag_wr_index = Signal(self.params.index_bits)
        self.tag_wr_en = Signal()
        self.tag_wr_data = Record(self.tag_data_layout)

        self.data_addr_layout = [("index", self.params.index_bits), ("offset", self.params.offset_bits)]

        self.data_rd_addr = Record(self.data_addr_layout)
        self.data_rd_data = Array([Signal(self.gp.isa.xlen) for _ in range(self.params.num_of_ways)])
        self.data_wr_addr = Record(self.data_addr_layout)
        self.data_wr_en = Signal()
        self.data_wr_data = Signal(self.gp.isa.xlen)

    def elaborate(self, platform) -> Module:
        m = Module()

        for i in range(self.params.num_of_ways):
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
                tag_mem_wp.en.eq(self.tag_wr_en & (self.way_wr_sel == i)),
            ]

            words_in_line = self.params.block_size_bytes // (self.gp.isa.xlen // 8)
            data_mem = Memory(width=self.gp.isa.xlen, depth=self.params.num_of_sets * words_in_line)
            data_mem_rp = data_mem.read_port()
            data_mem_wp = data_mem.write_port()
            m.submodules[f"data_mem_{i}_rp"] = data_mem_rp
            m.submodules[f"data_mem_{i}_wp"] = data_mem_wp

            # We address the data RAM using machine words, so we have to
            # discard a few least significant bits from the address.
            redundant_offset_bits = log2_int(self.gp.isa.xlen // 8)
            rd_addr = Cat(self.data_rd_addr.offset, self.data_rd_addr.index)[redundant_offset_bits:]
            wr_addr = Cat(self.data_wr_addr.offset, self.data_wr_addr.index)[redundant_offset_bits:]

            m.d.comb += [
                self.data_rd_data[i].eq(data_mem_rp.data),
                data_mem_rp.addr.eq(rd_addr),
                data_mem_wp.addr.eq(wr_addr),
                data_mem_wp.data.eq(self.data_wr_data),
                data_mem_wp.en.eq(self.data_wr_en & (self.way_wr_sel == i)),
            ]

        return m


class SimpleWBCacheRefiller(Elaboratable):
    def __init__(self, gen_params: GenParams, cache_params: ICacheParameters, wb_master: WishboneMaster):
        self.gp = gen_params
        self.cache_params = cache_params
        self.wb_master = wb_master

        layouts = self.gp.get(ICacheLayouts)
        self.start_refill = Method(i=layouts.start_refill)
        self.accept_refill = Method(o=layouts.accept_refill)

    def elaborate(self, platform) -> Module:
        m = Module()

        bytes_in_word = self.gp.isa.xlen // 8
        words_in_line = self.cache_params.block_size_bytes // bytes_in_word

        refill_address = Signal(self.gp.isa.xlen - self.cache_params.offset_bits)
        refill_active = Signal()
        word_counter = Signal(log2_int(words_in_line))

        with Transaction().body(m, request=refill_active):
            self.wb_master.request(
                m,
                addr=Cat(word_counter, refill_address),
                data=0,
                we=0,
                sel=Repl(1, self.wb_master.wb_params.data_width // self.wb_master.wb_params.granularity),
            )

        @def_method(m, self.start_refill, ready=~refill_active)
        def _(addr) -> None:
            m.d.sync += refill_address.eq(addr[self.cache_params.offset_bits :])
            m.d.sync += refill_active.eq(1)
            m.d.sync += word_counter.eq(0)

        @def_method(m, self.accept_refill, ready=refill_active)
        def _():
            fetched = self.wb_master.result(m)

            last = (word_counter == (words_in_line - 1)) | fetched.err

            m.d.sync += word_counter.eq(word_counter + 1)
            with m.If(last):
                m.d.sync += refill_active.eq(0)

            return {
                "addr": Cat(Repl(0, log2_int(bytes_in_word)), word_counter, refill_address),
                "data": fetched.data,
                "error": fetched.err,
                "last": last,
            }

        return m
