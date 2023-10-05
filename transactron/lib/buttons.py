from amaranth import *
from ..core import *

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
        argument, returns a `Record`.
    btn: Signal, in
        The button input.
    dat: Record, in
        The data input.
    """

    def __init__(self, layout: MethodLayout):
        """
        Parameters
        ----------
        layout: record layout
            The data format for the input.
        """
        self.get = Method(o=layout)
        self.btn = Signal()
        self.dat = Record(layout)

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
        The method for retrieving data from the input. Accepts a `Record`,
        returns empty result.
    btn: Signal, in
        The button input.
    dat: Record, out
        The data output.
    """

    def __init__(self, layout: MethodLayout):
        """
        Parameters
        ----------
        layout: record layout
            The data format for the output.
        """
        self.put = Method(i=layout)
        self.btn = Signal()
        self.dat = Record(layout)

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
