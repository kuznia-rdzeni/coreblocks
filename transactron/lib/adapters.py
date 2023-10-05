from amaranth import *
from ..core import *
from ..core import SignalBundle
from typing import Optional

__all__ = [
    "AdapterBase",
    "AdapterTrans",
    "Adapter",
]


class AdapterBase(Elaboratable):
    data_in: Record
    data_out: Record

    def __init__(self, iface: Method):
        self.iface = iface
        self.en = Signal()
        self.done = Signal()

    def debug_signals(self) -> SignalBundle:
        return [self.en, self.done, self.data_in, self.data_out]


class AdapterTrans(AdapterBase):
    """Adapter transaction.

    Creates a transaction controlled by plain Amaranth signals. Allows to
    expose a method to plain Amaranth code, including testbenches.

    Attributes
    ----------
    en: Signal, in
        Activates the transaction (sets the `request` signal).
    done: Signal, out
        Signals that the transaction is performed (returns the `grant`
        signal).
    data_in: Record, in
        Data passed to the `iface` method.
    data_out: Record, out
        Data returned from the `iface` method.
    """

    def __init__(self, iface: Method):
        """
        Parameters
        ----------
        iface: Method
            The method to be called by the transaction.
        """
        super().__init__(iface)
        self.data_in = Record.like(iface.data_in)
        self.data_out = Record.like(iface.data_out)

    def elaborate(self, platform):
        m = TModule()

        # this forces data_in signal to appear in VCD dumps
        data_in = Signal.like(self.data_in)
        m.d.comb += data_in.eq(self.data_in)

        with Transaction(name=f"AdapterTrans_{self.iface.name}").body(m, request=self.en):
            data_out = self.iface(m, data_in)
            m.d.top_comb += self.data_out.eq(data_out)
            m.d.comb += self.done.eq(1)

        return m


class Adapter(AdapterBase):
    """Adapter method.

    Creates a method controlled by plain Amaranth signals. One of the
    possible uses is to mock a method in a testbench.

    Attributes
    ----------
    en: Signal, in
        Activates the method (sets the `ready` signal).
    done: Signal, out
        Signals that the method is called (returns the `run` signal).
    data_in: Record, in
        Data returned from the defined method.
    data_out: Record, out
        Data passed as argument to the defined method.
    """

    def __init__(self, *, name: Optional[str] = None, i: MethodLayout = (), o: MethodLayout = ()):
        """
        Parameters
        ----------
        i: record layout
            The input layout of the defined method.
        o: record layout
            The output layout of the defined method.
        """
        super().__init__(Method(name=name, i=i, o=o))
        self.data_in = Record.like(self.iface.data_out)
        self.data_out = Record.like(self.iface.data_in)

    def elaborate(self, platform):
        m = TModule()

        # this forces data_in signal to appear in VCD dumps
        data_in = Signal.like(self.data_in)
        m.d.comb += data_in.eq(self.data_in)

        @def_method(m, self.iface, ready=self.en)
        def _(arg):
            m.d.top_comb += self.data_out.eq(arg)
            m.d.comb += self.done.eq(1)
            return data_in

        return m
