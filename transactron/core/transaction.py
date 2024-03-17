from transactron.utils import *
from amaranth import *
from amaranth import tracer
from typing import Optional, Iterator, TYPE_CHECKING
from .transaction_base import *
from .keys import *
from contextlib import contextmanager

if TYPE_CHECKING:
    from .tmodule import TModule
    from .manager import TransactionManager

__all__ = ["Transaction"]


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
    runnable: Signal, out
        Signals that all used methods are ready.
    grant: Signal, out
        Signals that the transaction is granted by the `TransactionManager`,
        and all used methods are called.
    """

    def __init__(
        self, *, name: Optional[str] = None, manager: Optional["TransactionManager"] = None, src_loc: int | SrcLoc = 0
    ):
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
        src_loc: int | SrcLoc
            How many stack frames deep the source location is taken from.
            Alternatively, the source location to use instead of the default.
        """
        super().__init__(src_loc=get_src_loc(src_loc))
        self.owner, owner_name = get_caller_class_name(default="$transaction")
        self.name = name or tracer.get_var_name(depth=2, default=owner_name)
        if manager is None:
            manager = DependencyContext.get().get_dependency(TransactionManagerKey())
        manager.add_transaction(self)
        self.request = Signal(name=self.owned_name + "_request")
        self.runnable = Signal(name=self.owned_name + "_runnable")
        self.grant = Signal(name=self.owned_name + "_grant")

    @contextmanager
    def body(self, m: "TModule", *, request: ValueLike = C(1)) -> Iterator["Transaction"]:
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

    def __repr__(self) -> str:
        return "(transaction {})".format(self.name)

    def debug_signals(self) -> SignalBundle:
        return [self.request, self.runnable, self.grant]
