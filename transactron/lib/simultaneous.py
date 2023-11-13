from amaranth import *
from ..core import *
from ..core import TransactionBase
from contextlib import contextmanager
from typing import Optional
from transactron.utils import ValueLike

__all__ = [
    "condition",
]


@contextmanager
def condition(m: TModule, *, nonblocking: bool = False, priority: bool = True):
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
    the other branches execute. Note that the default branch can run
    even if some of the conditions are true, but their branches can't
    execute for other reasons.

    Parameters
    ----------
    m : TModule
        A module where the condition is defined.
    nonblocking : bool
        States that the condition should not block the containing method
        or transaction from running, even when every branch cannot run.
        If `nonblocking` is false and every branch cannot run (because of
        a false condition or disabled called methods), the whole method
        or transaction will be stopped from running.
    priority : bool
        States that the conditions are not mutually exclusive and should
        be tested in order. This influences the scheduling order of generated
        transactions.

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

    @contextmanager
    def branch(cond: Optional[ValueLike] = None):
        nonlocal last
        if last:
            raise RuntimeError("Condition clause added after catch-all")
        req = cond if cond is not None else 1
        name = f"{this.name}_cond{len(transactions)}"
        with (transaction := Transaction(name=name)).body(m, request=req):
            yield
        if transactions and priority:
            transactions[-1].schedule_before(transaction)
        if cond is None:
            last = True
            if not priority:
                for transaction0 in transactions:
                    transaction0.schedule_before(transaction)
        transactions.append(transaction)

    yield branch

    if nonblocking and not last:
        with branch():
            pass

    this.simultaneous_alternatives(*transactions)
