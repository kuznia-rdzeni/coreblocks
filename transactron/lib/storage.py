from amaranth import *
from amaranth.utils import *
import amaranth.lib.memory as memory
import amaranth_types.memory as amemory

from transactron.utils.transactron_helpers import from_method_layout, make_layout
from ..core import *
from ..utils import SrcLoc, get_src_loc, MultiPriorityEncoder
from typing import Optional
from transactron.utils import LayoutList, MethodLayout

__all__ = ["MemoryBank", "ContentAddressableMemory", "AsyncMemoryBank"]


class MemoryBank(Elaboratable):
    """MemoryBank module.

    Provides a transactional interface to synchronous Amaranth Memory with arbitrary
    number of read and write ports. It supports optionally writing with given granularity.

    Attributes
    ----------
    read_reqs: list[Method]
        The read request methods, one for each read port. Accepts an `addr` from which data should be read.
        Only ready if there is there is a place to buffer response. After calling `read_reqs[i]`, the result
        will be available via the method `read_resps[i]`.
    read_resps: list[Method]
        The read response methods, one for each read port. Return `data_layout` View which was saved on `addr` given
        by last corresponding `read_reqs` method call. Only ready after corresponding `read_reqs` call.
    writes: list[Method]
        The write methods, one for each write port. Accepts write address `addr`, `data` in form of `data_layout`
        and optionally `mask` if `granularity` is not None. `1` in mask means that appropriate part should be written.
    read_req: Method
        The only method from `read_reqs`, if the memory has a single read port. If it has more ports, this method
        is unavailable and `read_reqs` should be used instead.
    read_resp: Method
        The only method from `read_resps`, if the memory has a single read port. If it has more ports, this method
        is unavailable and `read_resps` should be used instead.
    write: Method
        The only method from `writes`, if the memory has a single write port. If it has more ports, this method
        is unavailable and `writes` should be used instead.
    """

    def __init__(
        self,
        *,
        data_layout: LayoutList,
        elem_count: int,
        granularity: Optional[int] = None,
        transparent: bool = False,
        read_ports: int = 1,
        write_ports: int = 1,
        memory_type: amemory.AbstractMemoryConstructor[int, Value] = memory.Memory,
        src_loc: int | SrcLoc = 0,
    ):
        """
        Parameters
        ----------
        data_layout: method layout
            The format of structures stored in the Memory.
        elem_count: int
            Number of elements stored in Memory.
        granularity: Optional[int]
            Granularity of write, forwarded to Amaranth. If `None` the whole structure is always saved at once.
            If not, the width of `data_layout` is split into `granularity` parts, which can be saved independently.
        transparent: bool
            Read port transparency, false by default. When a read port is transparent, if a given memory address
            is read and written in the same clock cycle, the read returns the written value instead of the value
            which was in the memory in that cycle.
        read_ports: int
            Number of read ports.
        write_ports: int
            Number of write ports.
        src_loc: int | SrcLoc
            How many stack frames deep the source location is taken from.
            Alternatively, the source location to use instead of the default.
        """
        self.src_loc = get_src_loc(src_loc)
        self.data_layout = make_layout(*data_layout)
        self.elem_count = elem_count
        self.granularity = granularity
        self.width = from_method_layout(self.data_layout).size
        self.addr_width = bits_for(self.elem_count - 1)
        self.transparent = transparent
        self.reads_ports = read_ports
        self.writes_ports = write_ports
        self.memory_type = memory_type

        self.read_reqs_layout: LayoutList = [("addr", self.addr_width)]
        write_layout = [("addr", self.addr_width), ("data", self.data_layout)]
        if self.granularity is not None:
            write_layout.append(("mask", self.width // self.granularity))
        self.writes_layout = make_layout(*write_layout)

        self.read_reqs = [Method(i=self.read_reqs_layout, src_loc=self.src_loc) for _ in range(read_ports)]
        self.read_resps = [Method(o=self.data_layout, src_loc=self.src_loc) for _ in range(read_ports)]
        self.writes = [Method(i=self.writes_layout, src_loc=self.src_loc) for _ in range(write_ports)]

        if read_ports == 1:
            self.read_req = self.read_reqs[0]
            self.read_resp = self.read_resps[0]
        if write_ports == 1:
            self.write = self.writes[0]

    def elaborate(self, platform) -> TModule:
        m = TModule()

        m.submodules.mem = mem = self.memory_type(shape=self.width, depth=self.elem_count, init=[])
        write_port = [mem.write_port() for _ in range(self.writes_ports)]
        read_port = [
            mem.read_port(transparent_for=write_port if self.transparent else []) for _ in range(self.reads_ports)
        ]
        read_output_valid = [Signal() for _ in range(self.reads_ports)]
        overflow_valid = [Signal() for _ in range(self.reads_ports)]
        overflow_data = [Signal(self.width) for _ in range(self.reads_ports)]

        # The read request method can be called at most twice when not reading the response.
        # The first result is stored in the overflow buffer, the second - in the read value buffer of the memory.
        # If the responses are always read as they arrive, overflow is never written and no stalls occur.

        for i in range(self.reads_ports):
            with m.If(read_output_valid[i] & ~overflow_valid[i] & self.read_reqs[i].run & ~self.read_resps[i].run):
                m.d.sync += overflow_valid[i].eq(1)
                m.d.sync += overflow_data[i].eq(read_port[i].data)

        @def_methods(m, self.read_resps, lambda i: read_output_valid[i] | overflow_valid[i])
        def _(i: int):
            with m.If(overflow_valid[i]):
                m.d.sync += overflow_valid[i].eq(0)
            with m.Else():
                m.d.sync += read_output_valid[i].eq(0)
            return Mux(overflow_valid[i], overflow_data[i], read_port[i].data)

        for i in range(self.reads_ports):
            m.d.comb += read_port[i].en.eq(0)  # because the init value is 1

        @def_methods(m, self.read_reqs, lambda i: ~overflow_valid[i])
        def _(i: int, addr):
            m.d.sync += read_output_valid[i].eq(1)
            m.d.comb += read_port[i].en.eq(1)
            m.d.comb += read_port[i].addr.eq(addr)

        @def_methods(m, self.writes)
        def _(i: int, arg):
            m.d.comb += write_port[i].addr.eq(arg.addr)
            m.d.comb += write_port[i].data.eq(arg.data)
            if self.granularity is None:
                m.d.comb += write_port[i].en.eq(1)
            else:
                m.d.comb += write_port[i].en.eq(arg.mask)

        return m


class ContentAddressableMemory(Elaboratable):
    """Content addresable memory

    This module implements a content-addressable memory (in short CAM) with Transactron interface.
    CAM is a type of memory where instead of predefined indexes there are used values fed in runtime
    as keys (similar as in python dictionary). To insert new entry a pair `(key, value)` has to be
    provided. Such pair takes an free slot which depends on internal implementation. To read value
    a `key` has to be provided. It is compared with every valid key stored in CAM. If there is a hit,
    a value is read. There can be many instances of the same key in CAM. In such case it is undefined
    which value will be read.


    .. warning::
        Pushing the value with index already present in CAM is an undefined behaviour.

    Attributes
    ----------
    read : Method
        Nondestructive read
    write : Method
        If index present - do update
    remove : Method
        Remove
    push : Method
        Inserts new data.
    """

    def __init__(self, address_layout: MethodLayout, data_layout: MethodLayout, entries_number: int):
        """
        Parameters
        ----------
        address_layout : LayoutLike
            The layout of the address records.
        data_layout : LayoutLike
            The layout of the data.
        entries_number : int
            The number of slots to create in memory.
        """
        self.address_layout = from_method_layout(address_layout)
        self.data_layout = from_method_layout(data_layout)
        self.entries_number = entries_number

        self.read = Method(i=[("addr", self.address_layout)], o=[("data", self.data_layout), ("not_found", 1)])
        self.remove = Method(i=[("addr", self.address_layout)])
        self.push = Method(i=[("addr", self.address_layout), ("data", self.data_layout)])
        self.write = Method(i=[("addr", self.address_layout), ("data", self.data_layout)], o=[("not_found", 1)])

    def elaborate(self, platform) -> TModule:
        m = TModule()

        address_array = Array(
            [Signal(self.address_layout, name=f"address_array_{i}") for i in range(self.entries_number)]
        )
        data_array = Array([Signal(self.data_layout, name=f"data_array_{i}") for i in range(self.entries_number)])
        valids = Signal(self.entries_number, name="valids")

        m.submodules.encoder_read = encoder_read = MultiPriorityEncoder(self.entries_number, 1)
        m.submodules.encoder_write = encoder_write = MultiPriorityEncoder(self.entries_number, 1)
        m.submodules.encoder_push = encoder_push = MultiPriorityEncoder(self.entries_number, 1)
        m.submodules.encoder_remove = encoder_remove = MultiPriorityEncoder(self.entries_number, 1)
        m.d.top_comb += encoder_push.input.eq(~valids)

        @def_method(m, self.push, ready=~valids.all())
        def _(addr, data):
            id = Signal(range(self.entries_number), name="id_push")
            m.d.top_comb += id.eq(encoder_push.outputs[0])
            m.d.sync += address_array[id].eq(addr)
            m.d.sync += data_array[id].eq(data)
            m.d.sync += valids.bit_select(id, 1).eq(1)

        @def_method(m, self.write)
        def _(addr, data):
            write_mask = Signal(self.entries_number, name="write_mask")
            m.d.top_comb += write_mask.eq(Cat([addr == stored_addr for stored_addr in address_array]) & valids)
            m.d.top_comb += encoder_write.input.eq(write_mask)
            with m.If(write_mask.any()):
                m.d.sync += data_array[encoder_write.outputs[0]].eq(data)
            return {"not_found": ~write_mask.any()}

        @def_method(m, self.read)
        def _(addr):
            read_mask = Signal(self.entries_number, name="read_mask")
            m.d.top_comb += read_mask.eq(Cat([addr == stored_addr for stored_addr in address_array]) & valids)
            m.d.top_comb += encoder_read.input.eq(read_mask)
            return {"data": data_array[encoder_read.outputs[0]], "not_found": ~read_mask.any()}

        @def_method(m, self.remove)
        def _(addr):
            rm_mask = Signal(self.entries_number, name="rm_mask")
            m.d.top_comb += rm_mask.eq(Cat([addr == stored_addr for stored_addr in address_array]) & valids)
            m.d.top_comb += encoder_remove.input.eq(rm_mask)
            with m.If(rm_mask.any()):
                m.d.sync += valids.bit_select(encoder_remove.outputs[0], 1).eq(0)

        return m


class AsyncMemoryBank(Elaboratable):
    """AsyncMemoryBank module.

    Provides a transactional interface to asynchronous Amaranth Memory with arbitrary number of
    read and write ports. It supports optionally writing with given granularity.

    Attributes
    ----------
    reads: list[Method]
        The read methods, one for each read port. Accepts an `addr` from which data should be read.
        The read response method. Return `data_layout` View which was saved on `addr` given by last
        `write` method call.
    writes: list[Method]
        The write methods, one for each write port. Accepts write address `addr`, `data` in form of `data_layout`
        and optionally `mask` if `granularity` is not None. `1` in mask means that appropriate part should be written.
    read: Method
        The only method from `reads`, if the memory has a single read port.
    write: Method
        The only method from `writes`, if the memory has a single write port.
    """

    def __init__(
        self,
        *,
        data_layout: LayoutList,
        elem_count: int,
        granularity: Optional[int] = None,
        read_ports: int = 1,
        write_ports: int = 1,
        memory_type: amemory.AbstractMemoryConstructor[int, Value] = memory.Memory,
        src_loc: int | SrcLoc = 0,
    ):
        """
        Parameters
        ----------
        data_layout: method layout
            The format of structures stored in the Memory.
        elem_count: int
            Number of elements stored in Memory.
        granularity: Optional[int]
            Granularity of write, forwarded to Amaranth. If `None` the whole structure is always saved at once.
            If not, the width of `data_layout` is split into `granularity` parts, which can be saved independently.
        read_ports: int
            Number of read ports.
        write_ports: int
            Number of write ports.
        src_loc: int | SrcLoc
            How many stack frames deep the source location is taken from.
            Alternatively, the source location to use instead of the default.
        """
        self.src_loc = get_src_loc(src_loc)
        self.data_layout = make_layout(*data_layout)
        self.elem_count = elem_count
        self.granularity = granularity
        self.width = from_method_layout(self.data_layout).size
        self.addr_width = bits_for(self.elem_count - 1)
        self.reads_ports = read_ports
        self.writes_ports = write_ports
        self.memory_type = memory_type

        self.read_reqs_layout: LayoutList = [("addr", self.addr_width)]
        write_layout = [("addr", self.addr_width), ("data", self.data_layout)]
        if self.granularity is not None:
            write_layout.append(("mask", self.width // self.granularity))
        self.writes_layout = make_layout(*write_layout)

        self.reads = [
            Method(i=self.read_reqs_layout, o=self.data_layout, src_loc=self.src_loc) for _ in range(read_ports)
        ]
        self.writes = [Method(i=self.writes_layout, src_loc=self.src_loc) for _ in range(write_ports)]

        if read_ports == 1:
            self.read = self.reads[0]
        if write_ports == 1:
            self.write = self.writes[0]

    def elaborate(self, platform) -> TModule:
        m = TModule()

        mem = self.memory_type(shape=self.width, depth=self.elem_count, init=[])
        m.submodules.mem = mem
        write_port = [mem.write_port() for _ in range(self.writes_ports)]
        read_port = [mem.read_port(domain="comb") for _ in range(self.reads_ports)]

        @def_methods(m, self.reads)
        def _(i: int, addr):
            m.d.comb += read_port[i].addr.eq(addr)
            return read_port[i].data

        @def_methods(m, self.writes)
        def _(i: int, arg):
            m.d.comb += write_port[i].addr.eq(arg.addr)
            m.d.comb += write_port[i].data.eq(arg.data)
            if self.granularity is None:
                m.d.comb += write_port[i].en.eq(1)
            else:
                m.d.comb += write_port[i].en.eq(arg.mask)

        return m
