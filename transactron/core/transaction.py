from amaranth import *
from amaranth import tracer
from typing import Optional, Iterator
from contextlib import contextmanager
from .transaction_base import TransactionBase
from .manager import TransactionManager, TransactionContext
from .modules import TModule
from .typing import SignalBundle, ValueLike
from .._utils import get_caller_class_name
__all__ = [
    "Transaction",
]

class Transaction(TransactionBase):
    """Transaction.

    A `Transaction` represents a task which needs to be regularly done.
    Execution of a `Transaction` always lasts a single clock cycle.
    A `Transaction` signals readiness for execution by setting the
    `request` signal. If the conditions for its execution are met, it
    can be granted by the `TransactionManager`.

    A `Transaction` can, as part of its execution, call a number of
    `Method`\\s. A `Transaction` can be granted only if every `Method`
    it runs is ready.

    A `Transaction` cannot execute concurrently with another, conflicting
    `Transaction`. Conflicts between `Transaction`\\s are either explicit
    or implicit. An explicit conflict is added using the `add_conflict`
    method. Implicit conflicts arise between pairs of `Transaction`\\s
    which use the same `Method`.

    A module which defines a `Transaction` should use `body` to
    describe used methods and the transaction's effect on the module state.
    The used methods should be called inside the `body`'s
    `with` block.

    Attributes
    ----------
    name: str
        Name of this `Transaction`.
    request: Signal, in
        Signals that the transaction wants to run. If omitted, the transaction
        is always ready. Defined in the constructor.
    grant: Signal, out
        Signals that the transaction is granted by the `TransactionManager`,
        and all used methods are called.
    """

    def __init__(self, *, name: Optional[str] = None, manager: Optional[TransactionManager] = None):
        """
        Parameters
        ----------
        name: str or None
            Name hint for this `Transaction`. If `None` (default) the name is
            inferred from the variable name this `Transaction` is assigned to.
            If the `Transaction` was not assigned, the name is inferred from
            the class name where the `Transaction` was constructed.
        manager: TransactionManager
            The `TransactionManager` controlling this `Transaction`.
            If omitted, the manager is received from `TransactionContext`.
        """
        super().__init__()
        self.owner, owner_name = get_caller_class_name(default="$transaction")
        self.name = name or tracer.get_var_name(depth=2, default=owner_name)
        if manager is None:
            manager = TransactionContext.get()
        manager.add_transaction(self)
        self.request = Signal(name=self.owned_name + "_request")
        self.grant = Signal(name=self.owned_name + "_grant")

    @contextmanager
    def body(self, m: TModule, *, request: ValueLike = C(1)) -> Iterator["Transaction"]:
        """Defines the `Transaction` body.

        This context manager allows to conveniently define the actions
        performed by a `Transaction` when it's granted. Each assignment
        added to a domain under `body` is guarded by the `grant` signal.
        Combinational assignments which do not need to be guarded by
        `grant` can be added to `m.d.top_comb` or `m.d.av_comb` instead of
        `m.d.comb`. `Method` calls can be performed under `body`.

        Parameters
        ----------
        m: TModule
            The module where the `Transaction` is defined.
        request: Signal
            Indicates that the `Transaction` wants to be executed. By
            default it is `Const(1)`, so it wants to be executed in
            every clock cycle.
        """
        if self.defined:
            raise RuntimeError(f"Transaction '{self.name}' already defined")
        self.def_order = next(TransactionBase.def_counter)

        m.d.av_comb += self.request.eq(request)
        with self.context(m):
            with m.AvoidedIf(self.grant):
                yield self
        self.defined = True

    def __repr__(self) -> str:
        return "(transaction {})".format(self.name)

    def debug_signals(self) -> SignalBundle:
        return [self.request, self.grant]
