from amaranth import *
from ..core import *
from typing import Optional
from transactron.core import RecordDict
from transactron.utils import assign

__all__ = ["MethodBrancher"]


class MethodBrancher:
    """Syntax sugar for calling the same method in different `m.If` branches.

    Sometimes it is handy to write:

    .. highlight:: python
    .. code-block:: python

        with Transaction().body(m):
            with m.If(cond):
                method(arg1)
            with m.Else():
                method(arg2)

    But such code is not allowed, because a method is called twice in a transaction.
    So normaly it has to be rewritten to:

    .. highlight:: python
    .. code-block:: python

        rec = Record(method.data_in.layout)
        with Transaction().body(m):
            with m.If(cond):
                m.d.comb += assign(rec, arg1)
            with m.Else():
                m.d.comb += assign(rec, arg2)
            method(rec)

    But such a form is less readable. `MethodBrancher` is designed to do this
    transformation automatically, so you can write:

    .. highlight:: python
    .. code-block:: python

        with Transaction().body(m):
            b_method = MethodBrancher(m, method)
            with m.If(cond):
                b_method(arg1)
            with m.Else():
                b_method(arg2)

    IMPORTANT: `MethodBrancher` should be constructed within a `Transaction` or
    `Method` that should call the passed `method`. It creates a method call
    as part of `__init__` function.
    """

    def __init__(self, m: TModule, method: Method):
        """
        Parameters
        ----------
        m : TModule
            Module to add connections to.
        method : Method
            Method to wrap.
        """
        self.m = m
        self.method = method
        self.rec_in = Record(method.data_in.layout)
        self.rec_out = Record(method.data_out.layout)
        self.valid = Signal()
        with self.m.If(self.valid):
            self.m.d.comb += self.rec_out.eq(method(m, self.rec_in))

    def __call__(self, arg: Optional[RecordDict] = None, /, **kwargs: RecordDict) -> Record:
        self.m.d.comb += assign(self.rec_in, arg if arg is not None else kwargs)
        self.m.d.comb += self.valid.eq(1)

        return self.rec_out
