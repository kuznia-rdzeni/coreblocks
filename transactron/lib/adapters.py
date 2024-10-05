from abc import abstractmethod
from typing import Optional
from amaranth import *
from amaranth.lib.wiring import Component, In, Out
from amaranth.lib.data import StructLayout, View

from ..utils import SrcLoc, get_src_loc, MethodStruct
from ..core import *
from ..utils._typing import type_self_kwargs_as, SignalBundle

__all__ = [
    "AdapterBase",
    "AdapterTrans",
    "Adapter",
]


class AdapterBase(Component):
    data_in: MethodStruct
    data_out: MethodStruct
    en: Signal
    done: Signal

    def __init__(self, iface: Method, layout_in: StructLayout, layout_out: StructLayout):
        super().__init__({"data_in": In(layout_in), "data_out": Out(layout_out), "en": In(1), "done": Out(1)})
        self.iface = iface

    def debug_signals(self) -> SignalBundle:
        return [self.en, self.done, self.data_in, self.data_out]

    @abstractmethod
    def elaborate(self, platform) -> TModule:
        raise NotImplementedError()


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
    data_in: View, in
        Data passed to the `iface` method.
    data_out: View, out
        Data returned from the `iface` method.
    """

    def __init__(self, iface: Method, *, src_loc: int | SrcLoc = 0):
        """
        Parameters
        ----------
        iface: Method
            The method to be called by the transaction.
        src_loc: int | SrcLoc
            How many stack frames deep the source location is taken from.
            Alternatively, the source location to use instead of the default.
        """
        super().__init__(iface, iface.layout_in, iface.layout_out)
        self.src_loc = get_src_loc(src_loc)

    def elaborate(self, platform):
        m = TModule()

        # this forces data_in signal to appear in VCD dumps
        data_in = Signal.like(self.data_in)
        m.d.comb += data_in.eq(self.data_in)

        with Transaction(name=f"AdapterTrans_{self.iface.name}", src_loc=self.src_loc).body(m, request=self.en):
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
    data_in: View, in
        Data returned from the defined method.
    data_out: View, out
        Data passed as argument to the defined method.
    validators: list of tuples of View, out and Signal, in
        Hooks for `validate_arguments`.
    """

    @type_self_kwargs_as(Method.__init__)
    def __init__(self, **kwargs):
        """
        Parameters
        ----------
        **kwargs
            Keyword arguments for Method that will be created.
            See transactron.core.Method.__init__ for parameters description.
        """

        kwargs["src_loc"] = get_src_loc(kwargs.setdefault("src_loc", 0))

        iface = Method(**kwargs)
        super().__init__(iface, iface.layout_out, iface.layout_in)
        self.validators: list[tuple[View[StructLayout], Signal]] = []
        self.with_validate_arguments: bool = False

    def set(self, with_validate_arguments: Optional[bool]):
        if with_validate_arguments is not None:
            self.with_validate_arguments = with_validate_arguments
        return self

    def elaborate(self, platform):
        m = TModule()

        # this forces data_in signal to appear in VCD dumps
        data_in = Signal.like(self.data_in)
        m.d.comb += data_in.eq(self.data_in)

        kwargs = {}

        if self.with_validate_arguments:

            def validate_arguments(arg: "View[StructLayout]"):
                ret = Signal()
                self.validators.append((arg, ret))
                return ret

            kwargs["validate_arguments"] = validate_arguments

        @def_method(m, self.iface, ready=self.en, **kwargs)
        def _(arg):
            m.d.top_comb += self.data_out.eq(arg)
            m.d.comb += self.done.eq(1)
            return data_in

        return m
