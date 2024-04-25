from amaranth import *

from ..utils import SrcLoc
from ..core import *
from ..core import TransactionBase
from contextlib import contextmanager
from typing import Optional
from transactron.utils import ValueLike

__all__ = [
    "condition",
]


@contextmanager
def condition(m: TModule, *, nonblocking: bool = False, priority: bool = False):
    """Conditions using simultaneous transactions.

    This context manager allows to easily define conditions utilizing
    nested transactions and the simultaneous transactions mechanism.
    It is similar to Amaranth's `If`, but allows to call different and
    possibly overlapping method sets in each branch. Each of the branches is
    defined using a separate nested transaction.

    Inside the condition body, branches can be added, which are guarded
    by Boolean conditions. A branch is considered for execution if its
    condition is true and the called methods can be run. A catch-all,
    default branch can be added, which can be executed only if none of
    the other branches execute. The condition of the default branch is
    the negated alternative of all the other conditions.

    Parameters
    ----------
    m : TModule
        A module where the condition is defined.
    nonblocking : bool
        States that the condition should not block the containing method
        or transaction from running, even when none of the branch
        conditions is true. In case of a blocking method call, the
        containing method or transaction is still blocked.
    priority : bool
        States that when conditions are not mutually exclusive and multiple
        branches could be executed, the first one will be selected. This
        influences the scheduling order of generated transactions.

    Examples
    --------
    .. highlight:: python
    .. code-block:: python

        with condition(m) as branch:
            with branch(cond1):
                ...
            with branch(cond2):
                ...
            with branch():  # default, optional
                ...
    """
    this = TransactionBase.get()
    transactions = list[Transaction]()
    last = False
    conds = list[Signal]()

    @contextmanager
    def branch(cond: Optional[ValueLike] = None, *, src_loc: int | SrcLoc = 2):
        nonlocal last
        if last:
            raise RuntimeError("Condition clause added after catch-all")
        req = Signal()
        m.d.top_comb += req.eq(cond if cond is not None else ~Cat(*conds).any())
        conds.append(req)
        name = f"{this.name}_cond{len(transactions)}"
        with (transaction := Transaction(name=name, src_loc=src_loc)).body(m, request=req):
            yield
        if transactions and priority:
            transactions[-1].schedule_before(transaction)
        if cond is None:
            last = True
        transactions.append(transaction)

    yield branch

    if nonblocking and not last:
        with branch():
            pass

    this.simultaneous_alternatives(*transactions)
