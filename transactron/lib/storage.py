from amaranth import *
from amaranth.utils import *
from ..core import *
from typing import Optional
from coreblocks.utils import assign, AssignType
from .reqres import ArgumentsToResultsZipper

__all__ = ["MemoryBank"]


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
        The read response method. Return `data_layout` Record which was saved on `addr` given by last
        `read_req` method call. Only ready after `read_req` call.
    write: Method
        The write method. Accepts `addr` where data should be saved, `data` in form of `data_layout`
        and optionally `mask` if `granularity` is not None. `1` in mask means that appropriate part should be written.
    """

    def __init__(
        self, *, data_layout: MethodLayout, elem_count: int, granularity: Optional[int] = None, safe_writes: bool = True
    ):
        """
        Parameters
        ----------
        data_layout: record layout
            The format of records stored in the Memory.
        elem_count: int
            Number of elements stored in Memory.
        granularity: Optional[int]
            Granularity of write, forwarded to Amaranth. If `None` the whole record is always saved at once.
            If not, the width of `data_layout` is split into `granularity` parts, which can be saved independently.
        safe_writes: bool
            Set to `False` if an optimisation can be done to increase throughput of writes. This will cause that
            writes will be reordered with respect to reads eg. in sequence "read A, write A X", read can return
            "X" even when write was called later. By default `True`, which disable optimisation.
        """
        self.data_layout = data_layout
        self.elem_count = elem_count
        self.granularity = granularity
        self.width = len(Record(self.data_layout))
        self.addr_width = bits_for(self.elem_count - 1)
        self.safe_writes = safe_writes

        self.read_req_layout = [("addr", self.addr_width)]
        self.write_layout = [("addr", self.addr_width), ("data", self.data_layout)]
        if self.granularity is not None:
            self.write_layout.append(("mask", self.width // self.granularity))

        self.read_req = Method(i=self.read_req_layout)
        self.read_resp = Method(o=self.data_layout)
        self.write = Method(i=self.write_layout)
        self._internal_read_resp_trans = None

    def elaborate(self, platform) -> TModule:
        m = TModule()

        mem = Memory(width=self.width, depth=self.elem_count)
        m.submodules.read_port = read_port = mem.read_port()
        m.submodules.write_port = write_port = mem.write_port()
        read_output_valid = Signal()
        prev_read_addr = Signal(self.addr_width)
        write_pending = Signal()
        write_req = Signal()
        write_args = Record(self.write_layout)
        write_args_prev = Record(self.write_layout)
        m.d.comb += read_port.addr.eq(prev_read_addr)

        zipper = ArgumentsToResultsZipper([("valid", 1)], self.data_layout)
        m.submodules.zipper = zipper

        self._internal_read_resp_trans = Transaction()
        with self._internal_read_resp_trans.body(m, request=read_output_valid):
            m.d.sync += read_output_valid.eq(0)
            zipper.write_results(m, read_port.data)

        write_trans = Transaction()
        with write_trans.body(m, request=write_req | (~read_output_valid & write_pending)):
            if self.safe_writes:
                with m.If(write_pending):
                    m.d.comb += assign(write_args, write_args_prev, fields=AssignType.ALL)
            m.d.sync += write_pending.eq(0)
            m.d.comb += write_port.addr.eq(write_args.addr)
            m.d.comb += write_port.data.eq(write_args.data)
            if self.granularity is None:
                m.d.comb += write_port.en.eq(1)
            else:
                m.d.comb += write_port.en.eq(write_args.mask)

        @def_method(m, self.read_resp)
        def _():
            output = zipper.read(m)
            return output.results

        @def_method(m, self.read_req, ~write_pending)
        def _(addr):
            m.d.sync += read_output_valid.eq(1)
            m.d.comb += read_port.addr.eq(addr)
            m.d.sync += prev_read_addr.eq(addr)
            zipper.write_args(m, valid=1)

        @def_method(m, self.write, ~write_pending)
        def _(arg):
            if self.safe_writes:
                with m.If((arg.addr == read_port.addr) & (read_output_valid | self.read_req.run)):
                    m.d.sync += write_pending.eq(1)
                    m.d.sync += assign(write_args_prev, arg, fields=AssignType.ALL)
                with m.Else():
                    m.d.comb += write_req.eq(1)
            else:
                m.d.comb += write_req.eq(1)
            m.d.comb += assign(write_args, arg, fields=AssignType.ALL)

        return m
