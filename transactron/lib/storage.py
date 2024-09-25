from amaranth import *
from amaranth.utils import *

from transactron.utils.transactron_helpers import from_method_layout, make_layout
from ..core import *
from ..utils import SrcLoc, get_src_loc, MultiPriorityEncoder
from typing import Optional
from transactron.utils import LayoutList, MethodLayout

__all__ = ["MemoryBank", "ContentAddressableMemory", "AsyncMemoryBank"]


class MemoryBank(Elaboratable):
    """MemoryBank module.

    Provides a transactional interface to synchronous Amaranth Memory with one
    read and one write port. It supports optionally writing with given granularity.

    Attributes
    ----------
    read_req: Method
        The read request method. Accepts an `addr` from which data should be read.
        Only ready if there is there is a place to buffer response.
    read_resp: Method
        The read response method. Return `data_layout` View which was saved on `addr` given by last
        `read_req` method call. Only ready after `read_req` call.
    write: Method
        The write method. Accepts `addr` where data should be saved, `data` in form of `data_layout`
        and optionally `mask` if `granularity` is not None. `1` in mask means that appropriate part should be written.
    """

    def __init__(
        self,
        *,
        data_layout: LayoutList,
        elem_count: int,
        granularity: Optional[int] = None,
        transparent: bool = False,
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

        self.read_req_layout: LayoutList = [("addr", self.addr_width)]
        write_layout = [("addr", self.addr_width), ("data", self.data_layout)]
        if self.granularity is not None:
            write_layout.append(("mask", self.width // self.granularity))
        self.write_layout = make_layout(*write_layout)

        self.read_req = Method(i=self.read_req_layout, src_loc=self.src_loc)
        self.read_resp = Method(o=self.data_layout, src_loc=self.src_loc)
        self.write = Method(i=self.write_layout, src_loc=self.src_loc)
        self._internal_read_resp_trans = None

    def elaborate(self, platform) -> TModule:
        m = TModule()

        mem = Memory(width=self.width, depth=self.elem_count)
        m.submodules.read_port = read_port = mem.read_port(transparent=self.transparent)
        m.submodules.write_port = write_port = mem.write_port()
        read_output_valid = Signal()
        overflow_valid = Signal()
        overflow_data = Signal(self.width)

        # The read request method can be called at most twice when not reading the response.
        # The first result is stored in the overflow buffer, the second - in the read value buffer of the memory.
        # If the responses are always read as they arrive, overflow is never written and no stalls occur.

        with m.If(read_output_valid & ~overflow_valid & self.read_req.run & ~self.read_resp.run):
            m.d.sync += overflow_valid.eq(1)
            m.d.sync += overflow_data.eq(read_port.data)

        @def_method(m, self.read_resp, read_output_valid | overflow_valid)
        def _():
            with m.If(overflow_valid):
                m.d.sync += overflow_valid.eq(0)
            with m.Else():
                m.d.sync += read_output_valid.eq(0)
            return Mux(overflow_valid, overflow_data, read_port.data)

        m.d.comb += read_port.en.eq(0)  # because the init value is 1

        @def_method(m, self.read_req, ~overflow_valid)
        def _(addr):
            m.d.sync += read_output_valid.eq(1)
            m.d.comb += read_port.en.eq(1)
            m.d.comb += read_port.addr.eq(addr)

        @def_method(m, self.write)
        def _(arg):
            m.d.comb += write_port.addr.eq(arg.addr)
            m.d.comb += write_port.data.eq(arg.data)
            if self.granularity is None:
                m.d.comb += write_port.en.eq(1)
            else:
                m.d.comb += write_port.en.eq(arg.mask)

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

    Provides a transactional interface to asynchronous Amaranth Memory with one
    read and one write port. It supports optionally writing with given granularity.

    Attributes
    ----------
    read: Method
        The read method. Accepts an `addr` from which data should be read.
        The read response method. Return `data_layout` View which was saved on `addr` given by last
        `read_req` method call.
    write: Method
        The write method. Accepts `addr` where data should be saved, `data` in form of `data_layout`
        and optionally `mask` if `granularity` is not None. `1` in mask means that appropriate part should be written.
    """

    def __init__(
        self, *, data_layout: LayoutList, elem_count: int, granularity: Optional[int] = None, src_loc: int | SrcLoc = 0
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

        self.read_req_layout: LayoutList = [("addr", self.addr_width)]
        write_layout = [("addr", self.addr_width), ("data", self.data_layout)]
        if self.granularity is not None:
            write_layout.append(("mask", self.width // self.granularity))
        self.write_layout = make_layout(*write_layout)

        self.read = Method(i=self.read_req_layout, o=self.data_layout, src_loc=self.src_loc)
        self.write = Method(i=self.write_layout, src_loc=self.src_loc)

    def elaborate(self, platform) -> TModule:
        m = TModule()

        mem = Memory(width=self.width, depth=self.elem_count)
        m.submodules.read_port = read_port = mem.read_port(domain="comb")
        m.submodules.write_port = write_port = mem.write_port()

        @def_method(m, self.read)
        def _(addr):
            m.d.comb += read_port.addr.eq(addr)
            return read_port.data

        @def_method(m, self.write)
        def _(arg):
            m.d.comb += write_port.addr.eq(arg.addr)
            m.d.comb += write_port.data.eq(arg.data)
            if self.granularity is None:
                m.d.comb += write_port.en.eq(1)
            else:
                m.d.comb += write_port.en.eq(arg.mask)

        return m
