from functools import reduce
import operator

from amaranth import *
from amaranth.utils import log2_int

from coreblocks.transactions.core import def_method
from coreblocks.transactions import Method, Transaction
from coreblocks.params import GenParams, ICacheLayouts
from coreblocks.utils._typing import ValueLike
from coreblocks.peripherals.wishbone import WishboneMaster


__all__ = ["ICacheParameters", "ICache"]


class ICacheParameters:
    """Parameters of the Instruction Cache.

    Parameters
    ----------
    num_of_ways: int
        Associativity of the cache. Defaults to 2 ways.
    num_of_sets: int
        Number of cache sets. Defaults to 128 sets.
    block_size_bytes: int
        The size of a single cache block in bytes. Defaults to 32 bytes.
    """

    def __init__(self, *, num_of_ways=2, num_of_sets=128, block_size_bytes=32):
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

        self.index_start_bit = self.offset_bits
        self.index_end_bit = self.offset_bits + self.index_bits - 1


class ICache(Elaboratable):
    """A simple set-associative instruction cache.

    The replacement policy is a pseudo random scheme. Every time a line is trashed, we select the next
    way we write to (we keep one global counter selecting the next way).

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
            fetch unit.
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

        self.addr_width = self.gp.isa.xlen

    def elaborate(self, platform) -> Module:
        m = Module()

        tag_bits = self.addr_width - self.params.offset_bits - self.params.index_bits
        words_in_line = self.params.block_size_bytes // (self.gp.isa.xlen // 8)

        def extract_index(addr: ValueLike) -> ValueLike:
            return addr[self.params.index_start_bit : self.params.index_end_bit + 1]

        def extract_tag(addr: ValueLike) -> ValueLike:
            return addr[-tag_bits:]

        def extract_d_ram_addr(addr: ValueLike) -> ValueLike:
            return addr[log2_int(words_in_line) : self.params.index_end_bit + 1]

        ways = Array(Record([("tag_hit", 1)]) for _ in range(self.params.num_of_ways))

        way_selector = Signal(len(ways))

        tag_read_addr = Signal(self.params.index_bits)
        tag_write_addr = Signal(self.params.index_bits)
        tag_write_en = Signal()
        tag_data_in = Signal(1 + tag_bits)

        data_read_addr = Signal(self.params.index_bits + self.params.offset_bits - log2_int(words_in_line))
        data_write_addr = Signal(self.params.index_bits)
        data_write_en = Signal()
        data_in = Signal(self.gp.isa.xlen)

        lookup_valid = Signal()
        lookup_addr = Signal(self.addr_width)

        resp_err = Signal()

        refill_start = Signal()
        refill_finish = Signal()
        refill_error = Signal()

        tag_hit_any = reduce(operator.or_, (way.tag_hit for way in ways))

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

        for i, way in range(ways):
            with m.If(way.tag_hit):
                m.d.comb += instr_out.eq(data_mem_rp)

        # Tag logic
        m.d.comb += [
            tag_read_addr.eq(extract_index(lookup_addr)),
            tag_write_addr.eq(extract_index(lookup_addr)),
            tag_data_in.eq(Cat(1, extract_tag(lookup_addr))),
            tag_write_en.eq(fsm.ongoing("REFILL") & refill_finish & ~refill_error),
        ]

        m.d.comb += data_read_addr.eq(extract_d_ram_addr(lookup_addr))

        for i, way in range(ways):
            # TAG RAMS
            # valid bit is the least significant bit
            tag_mem = Memory(width=1 + tag_bits, depth=self.params.num_of_sets)
            tag_mem_rp = tag_mem.read_port()
            tag_mem_wp = tag_mem.write_port()
            m.submodules[f"tag_mem_{i}"] = tag_mem

            tag_valid = tag_mem_rp.data[0]
            tag_out = tag_mem_rp.data[1:]

            m.d.comb += [
                way.tag_hit.eq(tag_valid & (tag_out == extract_tag(lookup_addr))),
                tag_mem_rp.addr.eq(tag_read_addr),
                tag_mem_wp.addr.eq(tag_write_addr),
                tag_mem_wp.data.eq(tag_data_in),
                tag_mem_wp.en.eq(tag_write_en & (way_selector == i)),
            ]

            # DATA RAMS
            data_mem = Memory(width=self.gp.isa.xlen, depth=self.params.num_of_sets * words_in_line)
            data_mem_rp = data_mem.read_port()
            data_mem_wp = data_mem.write_port()
            m.submodules[f"data_mem_{i}"] = data_mem

            m.d.comb += [
                data_mem_rp.addr.eq(data_read_addr),
                data_mem_wp.addr.eq(data_write_addr),
                data_mem_wp.data.eq(data_in),
                data_mem_wp.en.eq(data_write_en & (way_selector == i)),
            ]

        with Transaction().body(m, request=refill_start):
            self.refiller_start(m, addr=Cat(Repl(0, self.params.offset_bits), lookup_addr[self.params.offset_bits :]))

        with Transaction().body(m):
            ret = self.refiller_accept(m)

            Transaction.comb += [data_write_addr.eq(extract_d_ram_addr(ret.addr)), data_in.eq(ret.data)]

            m.d.comb += data_write_en.eq(1)
            m.d.comb += refill_finish.eq(ret.finish)
            m.d.comb += refill_error.eq(ret.error)
            m.d.sync += resp_err.eq(ret.error)

        @def_method(m, self.accept_res, ready=resp_ready)
        def _() -> ValueLike:
            m.d.sync += lookup_valid.eq(0)
            m.d.sync += (resp_err.eq(0),)
            return {
                "instr": instr_out,
                "error": resp_err,
            }

        @def_method(m, self.issue_req, ready=fsm.ongoing("LOOKUP") & ~refill_start)
        def _(addr) -> None:
            m.d.comb += tag_read_addr.eq(extract_index(addr))
            m.d.comb += data_read_addr.eq(extract_d_ram_addr(addr))

            m.d.sync += lookup_addr.eq(addr)
            m.d.sync += lookup_valid.eq(1)

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
                sel=Repl(1, len(self.wb_master.wb_layout["sel"])),
            )

        @def_method(m, self.start_refill, ready=~refill_active)
        def _(addr) -> None:
            m.d.sync += refill_address.eq(addr[self.cache_params.offset_bits :])
            m.d.sync += refill_active.eq(1)
            m.d.sync += word_counter.eq(0)

        @def_method(m, self.accept_refill)
        def _() -> ValueLike:
            fetched = self.wb_master.result(m)

            last = word_counter == (words_in_line - 1) | fetched.err

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
