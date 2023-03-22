from functools import reduce
import operator

from amaranth import *
from amaranth.utils import log2_int

from coreblocks.transactions.core import def_method
from coreblocks.transactions import Method, Transaction
from coreblocks.params import GenParams, ICacheLayouts
from coreblocks.utils._typing import ValueLike
from coreblocks.utils import assign
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

    The replacement policy is a pseudo random scheme. Every time a line is trashed, we select the next
    way we write to (we keep one global counter for selecting the next way).

    Assumes that address is always a multiple of 4 (in bytes). RISC-V specification requires
    that instructions are 4 byte aligned. Extension C, however, adds 16-bit instructions, but
    this should be handled by the user of the cache.

    Address mapping example:
     31          16 15 14 13 12 11 10 09 08 07 06 05 04 03 02 01 00
    |--------------|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
    +--------------------+--------------------------+--------------+
    | Tag                | Index                    | Offset       |

    TODO - write doc
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
        TODO - write doc
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

        self.accept_res.schedule_before(self.issue_req)

    def elaborate(self, platform) -> Module:
        m = Module()

        def extract_offset(addr: Value) -> ValueLike:
            return addr[: self.params.offset_bits]

        def extract_index(addr: Value) -> ValueLike:
            return addr[self.params.index_start_bit : self.params.index_end_bit + 1]

        def extract_tag(addr: Value) -> ValueLike:
            return addr[-self.params.tag_bits :]

        m.submodules.mem = self.mem = ICacheMemory(self.gp, self.params)

        way_selector = Signal(log2_int(self.params.num_of_ways))

        lookup_valid = Signal()
        lookup_addr = Signal(self.params.addr_width)

        # Address directly forwarded from issue_req method.
        forwarded_addr = Signal(self.params.addr_width)

        resp_err = Signal()

        refill_start = Signal()
        refill_finish = Signal()
        refill_error = Signal()

        tag_hit = [tag_data.valid & tag_data.tag == lookup_addr for tag_data in self.mem.tag_rd_data]
        tag_hit_any = reduce(operator.or_, tag_hit)

        # Replacement policy
        with m.If(refill_finish):
            m.d.sync += way_selector.eq(way_selector + 1)

        # State machine logic
        with m.FSM() as fsm:
            with m.State("LOOKUP"):
                with m.If(lookup_valid & ~tag_hit_any):
                    m.d.comb += refill_start.eq(1)
                    m.next = "REFILL"

            with m.State("REFILL"):
                with m.If(refill_finish):
                    m.next = "LOOKUP"

        # Instruction output
        resp_ready = lookup_valid & fsm.ongoing("LOOKUP") & (tag_hit_any | resp_err)
        instr_out = Signal(self.gp.isa.ilen)

        for i in range(self.params.num_of_ways):
            with m.If(tag_hit[i]):
                m.d.comb += instr_out.eq(self.mem.data_rd_data[i]) # TODO(jurb): this doesn't work on rv64

        # Tag writing logic
        m.d.comb += [
            self.mem.tag_wr_index.eq(extract_index(lookup_addr)),
            self.mem.tag_wr_data.valid.eq(1),
            self.mem.tag_wr_data.tag.eq(extract_tag(lookup_addr)),
            self.mem.tag_wr_en.eq(fsm.ongoing("REFILL") & refill_finish & ~refill_error),
        ]

        # Memory read addresses
        read_addr = Mux(fsm.ongoing("REFILL"), lookup_addr, forwarded_addr)
        m.d.comb += [
            self.mem.tag_rd_index.eq(extract_index(read_addr)),
            self.mem.data_rd_addr.index.eq(extract_index(read_addr)),
            self.mem.data_rd_addr.offset.eq(extract_offset(read_addr)),
        ]

        with Transaction().body(m, request=refill_start):
            self.refiller_start(m, addr=Cat(Repl(0, self.params.offset_bits), lookup_addr[self.params.offset_bits :]))

        with Transaction().body(m):
            ret = self.refiller_accept(m)

            Transaction.comb += [
                self.mem.data_wr_addr.index.eq(extract_index(ret.addr)),
                self.mem.data_wr_addr.offset.eq(extract_offset(ret.addr)),
            ]

            m.d.comb += self.mem.data_wr_en.eq(1)
            m.d.comb += refill_finish.eq(ret.last)
            m.d.comb += refill_error.eq(ret.error)
            m.d.sync += resp_err.eq(ret.error)

        @def_method(m, self.accept_res, ready=resp_ready)
        def _():
            m.d.sync += lookup_valid.eq(0)
            m.d.sync += resp_err.eq(0)

            return {
                "instr": instr_out,
                "error": resp_err,
            }

        @def_method(m, self.issue_req, ready=fsm.ongoing("LOOKUP") & ~refill_start)
        def _(addr) -> None:
            Method.comb += forwarded_addr.eq(addr)

            m.d.sync += lookup_addr.eq(addr)
            m.d.sync += lookup_valid.eq(1)

        return m


class ICacheMemory(Elaboratable):
    """
    TODO - write doc
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

            # We address the data RAM using machine words, so we have to discard a few bits from the address.
            redundant_offset_bits = log2_int(self.gp.isa.xlen_log // 8)
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

        @def_method(m, self.accept_refill)
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
