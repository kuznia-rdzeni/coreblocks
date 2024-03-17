from amaranth import *

from transactron.utils.transactron_helpers import from_method_layout
from ..core import *
from ..utils import SrcLoc, get_src_loc, MethodLayout

__all__ = ["ClickIn", "ClickOut"]


class ClickIn(Elaboratable):
    """Clicked input.

    Useful for interactive simulations or FPGA button/switch interfaces.
    On a rising edge (tested synchronously) of `btn`, the `get` method
    is enabled, which returns the data present on `dat` at the time.
    Inputs are synchronized.

    Attributes
    ----------
    get: Method
        The method for retrieving data from the input. Accepts an empty
        argument, returns a structure.
    btn: Signal, in
        The button input.
    dat: MethodStruct, in
        The data input.
    """

    def __init__(self, layout: MethodLayout, src_loc: int | SrcLoc = 0):
        """
        Parameters
        ----------
        layout: method layout
            The data format for the input.
        src_loc: int | SrcLoc
            How many stack frames deep the source location is taken from.
            Alternatively, the source location to use instead of the default.
        """
        src_loc = get_src_loc(src_loc)
        self.get = Method(o=layout, src_loc=src_loc)
        self.btn = Signal()
        self.dat = Signal(from_method_layout(layout))

    def elaborate(self, platform):
        m = TModule()

        btn1 = Signal()
        btn2 = Signal()
        dat1 = Signal.like(self.dat)
        m.d.sync += btn1.eq(self.btn)
        m.d.sync += btn2.eq(btn1)
        m.d.sync += dat1.eq(self.dat)
        get_ready = Signal()
        get_data = Signal.like(self.dat)

        @def_method(m, self.get, ready=get_ready)
        def _():
            m.d.sync += get_ready.eq(0)
            return get_data

        with m.If(~btn2 & btn1):
            m.d.sync += get_ready.eq(1)
            m.d.sync += get_data.eq(dat1)

        return m


class ClickOut(Elaboratable):
    """Clicked output.

    Useful for interactive simulations or FPGA button/LED interfaces.
    On a rising edge (tested synchronously) of `btn`, the `put` method
    is enabled, which, when called, changes the value of the `dat` signal.

    Attributes
    ----------
    put: Method
        The method for retrieving data from the input. Accepts a structure,
        returns empty result.
    btn: Signal, in
        The button input.
    dat: MethodStruct, out
        The data output.
    """

    def __init__(self, layout: MethodLayout, *, src_loc: int | SrcLoc = 0):
        """
        Parameters
        ----------
        layout: method layout
            The data format for the output.
        src_loc: int | SrcLoc
            How many stack frames deep the source location is taken from.
            Alternatively, the source location to use instead of the default.
        """
        src_loc = get_src_loc(src_loc)
        self.put = Method(i=layout, src_loc=src_loc)
        self.btn = Signal()
        self.dat = Signal(from_method_layout(layout))

    def elaborate(self, platform):
        m = TModule()

        btn1 = Signal()
        btn2 = Signal()
        m.d.sync += btn1.eq(self.btn)
        m.d.sync += btn2.eq(btn1)

        @def_method(m, self.put, ready=~btn2 & btn1)
        def _(arg):
            m.d.sync += self.dat.eq(arg)

        return m
