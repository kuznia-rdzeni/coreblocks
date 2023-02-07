from collections import defaultdict
from contextlib import contextmanager
from enum import Enum, auto
from typing import Callable, ClassVar, Mapping, TypeAlias, TypedDict, Union, Optional, Tuple, Iterator
from types import MethodType
from graphlib import TopologicalSorter
from typing_extensions import Self
from amaranth import *
from amaranth import tracer
from amaranth.hdl.ast import Assign, Statement
from ._utils import *
from ..utils._typing import StatementLike, ValueLike, DebugSignals
from .graph import Owned, OwnershipGraph, Direction

__all__ = [
    "Priority",
    "TransactionManager",
    "TransactionContext",
    "TransactionModule",
    "Transaction",
    "Method",
    "eager_deterministic_cc_scheduler",
    "trivial_roundrobin_cc_scheduler",
    "def_method",
]


TransactionGraph: TypeAlias = Graph["Transaction"]
TransactionGraphCC: TypeAlias = GraphCC["Transaction"]
PriorityOrder: TypeAlias = dict["Transaction", int]
TransactionScheduler: TypeAlias = Callable[
    ["TransactionManager", Module, TransactionGraph, TransactionGraphCC, PriorityOrder], None
]
RecordDict: TypeAlias = ValueLike | Mapping[str, "RecordDict"]


class Priority(Enum):
    UNDEFINED = auto()
    LEFT = auto()
    RIGHT = auto()


class RelationBase(TypedDict):
    end: Union["Transaction", "Method"]
    priority: Priority
    conflict: bool


class Relation(RelationBase):
    start: Union["Transaction", "Method"]


def eager_deterministic_cc_scheduler(
    manager: "TransactionManager", m: Module, gr: TransactionGraph, cc: TransactionGraphCC, porder: PriorityOrder
):
    """eager_deterministic_cc_scheduler

    This function generates an eager scheduler for the transaction
    subsystem. It isn't fair, because it starts transactions using
    transaction index in `cc` as a priority. Transaction with the lowest
    index has the highest priority.

    If there are two different transactions which have no conflicts then
    they will be started concurrently.

    Parameters
    ----------
    manager : TransactionManager
        TransactionManager which uses this instance of scheduler for
        arbitrating which agent should get a grant signal.
    m : Module
        Module to which signals and calculations should be connected.
    gr : TransactionGraph
        Graph of conflicts between transactions, where vertices are transactions and edges are conflicts.
    cc : Set[Transaction]
        Connected components of the graph `gr` for which scheduler
        should be generated.
    porder : PriorityOrder
        Linear ordering of transactions which is consistent with priority constraints.
    """
    ccl = list(cc)
    ccl.sort(key=lambda transaction: porder[transaction])
    for k, transaction in enumerate(ccl):
        ready = [method.ready for method in manager.methods_by_transaction[transaction]]
        runnable = Cat(ready).all()
        conflicts = [ccl[j].grant for j in range(k) if ccl[j] in gr[transaction]]
        noconflict = ~Cat(conflicts).any()
        m.d.comb += transaction.grant.eq(transaction.request & runnable & noconflict)


def trivial_roundrobin_cc_scheduler(
    manager: "TransactionManager", m: Module, gr: TransactionGraph, cc: TransactionGraphCC, porder: PriorityOrder
):
    """trivial_roundrobin_cc_scheduler

    This function generates a simple round-robin scheduler for the transaction
    subsystem. In a one cycle there will be at most one transaction granted
    (in a given connected component of the conflict graph), even if there is
    another ready, non-conflicting, transaction. It is mainly for testing
    purposes.

    Parameters
    ----------
    manager : TransactionManager
        TransactionManager which uses this instance of scheduler for
        arbitrating which agent should get grant signal.
    m : Module
        Module to which signals and calculations should be connected.
    gr : TransactionGraph
        Graph of conflicts between transactions, where vertices are transactions and edges are conflicts.
    cc : Set[Transaction]
        Connected components of the graph `gr` for which scheduler
        should be generated.
    porder : PriorityOrder
        Linear ordering of transactions which is consistent with priority constraints.
    """
    sched = Scheduler(len(cc))
    m.submodules += sched
    for k, transaction in enumerate(cc):
        methods = manager.methods_by_transaction[transaction]
        ready = Signal(len(methods))
        for n, method in enumerate(methods):
            m.d.comb += ready[n].eq(method.ready)
        runnable = ready.all()
        m.d.comb += sched.requests[k].eq(transaction.request & runnable)
        m.d.comb += transaction.grant.eq(sched.grant[k] & sched.valid)


class TransactionManager(Elaboratable):
    """Transaction manager

    This module is responsible for granting `Transaction`\\s and running
    `Method`\\s. It takes care that two conflicting `Transaction`\\s
    are never granted in the same clock cycle.
    """

    def __init__(self, cc_scheduler: TransactionScheduler = eager_deterministic_cc_scheduler):
        self.transactions: list[Transaction] = []
        self.relations: list[Relation] = []
        self.cc_scheduler = MethodType(cc_scheduler, self)

    def add_transaction(self, transaction: "Transaction"):
        self.transactions.append(transaction)

    def _conflict_graph(self) -> Tuple[TransactionGraph, TransactionGraph, PriorityOrder]:
        """_conflict_graph

        This function generates the graph of transaction conflicts. Conflicts
        between transactions can be explicit or implicit. Two transactions
        conflict explicitly, if a conflict was added between the transactions
        or the methods used by them via `add_conflict`. Two transactions
        conflict implicitly if they are both using the same method.

        Created graph is undirected. Transactions are nodes in that graph
        and conflict between two transactions is marked as an edge. In such
        representation connected components are sets of transactions which can
        potentially conflict so there is a need to arbitrate between them.
        On the other hand when two transactions are in different connected
        components, then they can be scheduled independently, because they
        will have no conflicts.

        This function also computes a linear ordering of transactions
        which is consistent with conflict priorities of methods and
        transactions. When priority constraints cannot be satisfied,
        an exception is thrown.

        Returns
        -------
        cgr : TransactionGraph
            Graph of conflicts between transactions, where vertices are transactions and edges are conflicts.
        rgr : TransactionGraph
            Graph of relations between transactions, which includes conflicts and orderings.
        porder : PriorityOrder
            Linear ordering of transactions which is consistent with priority constraints.
        """

        def end_trans(end: Transaction | Method) -> list[Transaction]:
            if isinstance(end, Method):
                return self.transactions_by_method[end]
            else:
                return [end]

        cgr: TransactionGraph = {}  # Conflict graph
        pgr: TransactionGraph = {}  # Priority graph
        rgr: TransactionGraph = {}  # Relation graph

        def add_edge(begin: Transaction, end: Transaction, priority: Priority, conflict: bool):
            rgr[begin].add(end)
            rgr[end].add(begin)
            if conflict:
                cgr[begin].add(end)
                cgr[end].add(begin)
            match priority:
                case Priority.LEFT:
                    pgr[end].add(begin)
                case Priority.RIGHT:
                    pgr[begin].add(end)

        for transaction in self.transactions:
            cgr[transaction] = set()
            pgr[transaction] = set()
            rgr[transaction] = set()

        for transaction, methods in self.methods_by_transaction.items():
            for method in methods:
                if method.nonexclusive:
                    continue
                for transaction2 in self.transactions_by_method[method]:
                    if transaction is not transaction2:
                        add_edge(transaction, transaction2, Priority.UNDEFINED, True)

        for relation in self.relations:
            for start in end_trans(relation["start"]):
                for end in end_trans(relation["end"]):
                    add_edge(start, end, relation["priority"], relation["conflict"])

        porder: PriorityOrder = {}

        for (k, transaction) in enumerate(TopologicalSorter(pgr).static_order()):
            porder[transaction] = k

        return cgr, rgr, porder

    def _call_graph(self, transaction: "Transaction", method: "Method", arg: ValueLike, enable: ValueLike):
        if not method.defined:
            raise RuntimeError("Trying to use method which is not defined yet")
        if method in self.method_uses[transaction]:
            raise RuntimeError("Method can't be called twice from the same transaction")
        self.method_uses[transaction][method] = (arg, enable)
        self.methods_by_transaction[transaction].append(method)
        self.transactions_by_method[method].append(transaction)
        for relation in method.relations:
            self.relations.append(Relation(**relation, start=method))
        for method, (arg, enable) in method.method_uses.items():
            self._call_graph(transaction, method, arg, enable)

    def elaborate(self, platform):

        self.methods_by_transaction = defaultdict[Transaction, list[Method]](list)
        self.transactions_by_method = defaultdict[Method, list[Transaction]](list)
        self.method_uses = defaultdict[Transaction, dict[Method, Tuple[ValueLike, ValueLike]]](dict)

        for transaction in self.transactions:
            for relation in transaction.relations:
                self.relations.append(Relation(**relation, start=transaction))
            for method, (arg, enable) in transaction.method_uses.items():
                self._call_graph(transaction, method, arg, enable)

        cgr, rgr, porder = self._conflict_graph()

        m = Module()

        for cc in _graph_ccs(rgr):
            self.cc_scheduler(m, cgr, cc, porder)

        for method, transactions in self.transactions_by_method.items():
            granted = Signal(len(transactions))
            for n, transaction in enumerate(transactions):
                (tdata, enable) = self.method_uses[transaction][method]
                m.d.comb += granted[n].eq(transaction.grant & enable)

                with m.If(transaction.grant):
                    m.d.comb += method.data_in.eq(tdata)
            runnable = granted.any()
            m.d.comb += method.run.eq(runnable)

        return m

    def visual_graph(self, fragment):
        graph = OwnershipGraph(fragment)
        for method, transactions in self.transactions_by_method.items():
            if len(method.data_in) > len(method.data_out):
                direction = Direction.IN
            elif len(method.data_in) < len(method.data_out):
                direction = Direction.OUT
            else:
                direction = Direction.INOUT
            graph.insert_node(method)
            for transaction in transactions:
                graph.insert_node(transaction)
                graph.insert_edge(transaction, method, direction)

        return graph


class TransactionContext:
    stack: list[TransactionManager] = []

    def __init__(self, manager: TransactionManager):
        self.manager = manager

    def __enter__(self):
        self.stack.append(self.manager)
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        top = self.stack.pop()
        assert self.manager is top

    @classmethod
    def get(cls) -> TransactionManager:
        if not cls.stack:
            raise RuntimeError("TransactionContext stack is empty")
        return cls.stack[-1]


class TransactionModule(Elaboratable):
    """
    `TransactionModule` is used as wrapper on `Module` class,
    which add support for transaction to the `Module`. It creates a
    `TransactionManager` which will handle transaction scheduling
    and can be used in definition of `Method`\\s and `Transaction`\\s.
    """

    def __init__(self, module: Module, manager: Optional[TransactionManager] = None):
        """
        Parameters
        ----------
        module: Module
                The `Module` which should be wrapped to add support for
                transactions and methods.
        """
        if manager is None:
            manager = TransactionManager()
        self.transactionManager = manager
        self.module = module

    def transaction_context(self) -> TransactionContext:
        return TransactionContext(self.transactionManager)

    def elaborate(self, platform):
        with self.transaction_context():
            for name in self.module._named_submodules:
                self.module._named_submodules[name] = Fragment.get(self.module._named_submodules[name], platform)
            for idx in range(len(self.module._anon_submodules)):
                self.module._anon_submodules[idx] = Fragment.get(self.module._anon_submodules[idx], platform)

        self.module.submodules += self.transactionManager

        return self.module


class _TransactionBaseStatements:
    def __init__(self):
        self.statements: list[Statement] = []

    def __iadd__(self, assigns: StatementLike):
        if TransactionBase.current is None:
            raise RuntimeError("No current body")
        for stmt in Statement.cast(assigns):
            self.statements.append(stmt)
        return self

    def __iter__(self):
        return self.statements.__iter__()

    def clear(self):
        return self.statements.clear()


class TransactionBase(Owned):
    current: ClassVar[Optional["TransactionBase"]] = None
    comb: ClassVar[_TransactionBaseStatements] = _TransactionBaseStatements()

    def __init__(self):
        self.method_uses: dict[Method, Tuple[ValueLike, ValueLike]] = dict()
        self.relations: list[RelationBase] = []

    def add_conflict(self, end: Union["Transaction", "Method"], priority: Priority = Priority.UNDEFINED) -> None:
        """Registers a conflict.

        Record that that the given `Transaction` or `Method` cannot execute
        simultaneously with this `Method` or `Transaction`. Typical reason
        is using a common resource (register write or memory port).

        Parameters
        ----------
        end: Transaction or Method
            The conflicting `Transaction` or `Method`
        priority: Priority, optional
            Is one of conflicting `Transaction`\\s or `Method`\\s prioritized?
            Defaults to undefined priority relation.
        """
        self.relations.append(RelationBase(end=end, priority=priority, conflict=True))

    def schedule_before(self, end: Union["Transaction", "Method"]) -> None:
        """Adds a priority relation.

        Record that that the given `Transaction` or `Method` needs to be
        scheduled before this `Method` or `Transaction`, without adding
        a conflict. Typical reason is data forwarding.

        Parameters
        ----------
        end: Transaction or Method
            The other `Transaction` or `Method`
        """
        self.relations.append(RelationBase(end=end, priority=Priority.RIGHT, conflict=False))

    def use_method(self, method: "Method", arg: ValueLike, enable: ValueLike):
        if method in self.method_uses:
            raise RuntimeError("Method can't be called twice from the same transaction")
        self.method_uses[method] = (arg, enable)

    @contextmanager
    def context(self) -> Iterator[Self]:
        if TransactionBase.current is not None:
            raise RuntimeError("Body inside body")
        assert not TransactionBase.comb.statements
        TransactionBase.current = self
        try:
            yield self
            assert not TransactionBase.comb.statements
        finally:
            TransactionBase.comb.clear()
            TransactionBase.current = None

    @classmethod
    def get(cls) -> Self:
        if TransactionBase.current is None:
            raise RuntimeError("No current body")
        if not isinstance(TransactionBase.current, cls):
            raise RuntimeError(f"Current body not a {cls.__name__}")
        return TransactionBase.current


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
        self.request = Signal()
        self.grant = Signal()

    @contextmanager
    def body(self, m: Module, *, request: ValueLike = C(1)) -> Iterator["Transaction"]:
        """Defines the `Transaction` body.

        This context manager allows to conveniently define the actions
        performed by a `Transaction` when it's granted. Each assignment
        added to a domain under `body` is guarded by the `grant` signal.
        Combinational assignments which do not need to be guarded by
        `grant` can be added to `Transaction.comb` instead of
        `m.d.comb`. `Method` calls can be performed under `body`.

        Parameters
        ----------
        m: Module
            The module where the `Transaction` is defined.
        request: Signal
            Indicates that the `Transaction` wants to be executed. By
            default it is `Const(1)`, so it wants to be executed in
            every clock cycle.
        """
        m.d.comb += self.request.eq(request)
        with self.context():
            with m.If(self.grant):
                yield self
            m.d.comb += TransactionBase.comb
            TransactionBase.comb.clear()

    def __repr__(self) -> str:
        return "(transaction {})".format(self.name)

    def debug_signals(self) -> DebugSignals:
        return [self.request, self.grant]


def _connect_rec_with_possibly_dict(dst: Value | Record, src: RecordDict) -> list[Assign]:
    if not isinstance(src, Mapping):
        return [dst.eq(src)]

    if not isinstance(dst, Record):
        raise TypeError("Cannot connect a dict of signals to a non-record.")

    exprs: list[Assign] = []
    for k, v in src.items():
        exprs += _connect_rec_with_possibly_dict(dst[k], v)

    # Make sure all fields of the record are specified in the dict.
    for field_name, _, _ in dst.layout:
        if field_name not in src:
            raise KeyError("Field {} is not specified in the dict.".format(field_name))

    return exprs


class Method(TransactionBase):
    """Transactional method.

    A `Method` serves to interface a module with external `Transaction`\\s
    or `Method`\\s. It can be called by at most once in a given clock cycle.
    When a given `Method` is required by multiple `Transaction`\\s
    (either directly, or indirectly via another `Method`) simultenaously,
    at most one of them is granted by the `TransactionManager`, and the rest
    of them must wait. (Non-exclusive methods are an exception to this
    behavior.) Calling a `Method` always takes a single clock cycle.

    Data is combinationally transferred between to and from `Method`\\s
    using Amaranth `Record`\\s. The transfer can take place in both directions
    at the same time: from the called `Method` to the caller (`data_out`)
    and from the caller to the called `Method` (`data_in`).

    A module which defines a `Method` should use `body` or `def_method`
    to describe the method's effect on the module state.

    Attributes
    ----------
    name: str
        Name of this `Method`.
    ready: Signal, in
        Signals that the method is ready to run in the current cycle.
        Typically defined by calling `body`.
    run: Signal, out
        Signals that the method is called in the current cycle by some
        `Transaction`. Defined by the `TransactionManager`.
    data_in: Record, out
        Contains the data passed to the `Method` by the caller
        (a `Transaction` or another `Method`).
    data_out: Record, in
        Contains the data passed from the `Method` to the caller
        (a `Transaction` or another `Method`). Typically defined by
        calling `body`.
    """

    def __init__(
        self, *, name: Optional[str] = None, i: MethodLayout = (), o: MethodLayout = (), nonexclusive: bool = False
    ):
        """
        Parameters
        ----------
        name: str or None
            Name hint for this `Method`. If `None` (default) the name is
            inferred from the variable name this `Method` is assigned to.
        i: record layout
            The format of `data_in`.
            An `int` corresponds to a `Record` with a single `data` field.
        o: record layout
            The format of `data_in`.
            An `int` corresponds to a `Record` with a single `data` field.
        nonexclusive: bool
            If true, the method is non-exclusive: it can be called by multiple
            transactions in the same clock cycle. If such a situation happens,
            the method still is executed only once, and each of the callers
            receive its output. Nonexclusive methods cannot have inputs.
        """
        super().__init__()
        self.owner, owner_name = get_caller_class_name(default="$method")
        self.name = name or tracer.get_var_name(depth=2, default=owner_name)
        self.ready = Signal()
        self.run = Signal()
        self.data_in = Record(i)
        self.data_out = Record(o)
        self.defined = False
        self.nonexclusive = nonexclusive
        if nonexclusive:
            assert len(self.data_in) == 0

    @staticmethod
    def like(other: "Method", *, name: Optional[str] = None) -> "Method":
        """Constructs a new `Method` based on another.

        The returned `Method` has the same input/output data layouts as the
        `other` `Method`.

        Parameters
        ----------
        other : Method
            The `Method` which serves as a blueprint for the new `Method`.
        name : str, optional
            Name of the new `Method`.

        Returns
        -------
        Method
            The freshly constructed `Method`.
        """
        return Method(name=name, i=other.data_in.layout, o=other.data_out.layout)

    def proxy(self, m: Module, method: "Method"):
        """Define as a proxy for another method.

        The calls to this method will be forwarded to `method`.

        Parameters
        ----------
        m : Module
            Module in which operations on signals should be executed,
            `proxy` uses the combinational domain only.
        method : Method
            Method for which this method is a proxy for.
        """
        m.d.comb += self.ready.eq(1)
        m.d.comb += self.data_out.eq(method.data_out)
        self.use_method(method, arg=self.data_in, enable=C(1))
        self.defined = True

    @contextmanager
    def body(self, m: Module, *, ready: ValueLike = C(1), out: ValueLike = C(0, 0)) -> Iterator[Record]:
        """Define method body

        The `body` context manager can be used to define the actions
        performed by a `Method` when it's run. Each assignment added to
        a domain under `body` is guarded by the `run` signal.
        Combinational assignments which do not need to be guarded by `run`
        can be added to `Method.comb` instead of `m.d.comb`. `Method`
        calls can be performed under `body`.

        Parameters
        ----------
        m : Module
            Module in which operations on signals should be executed,
            `body` uses the combinational domain only.
        ready : Signal, in
            Signal to indicate if the method is ready to be run. By
            default it is `Const(1)`, so the method is always ready.
            Assigned combinationially to the `ready` attribute.
        out : Record, in
            Data generated by the `Method`, which will be passed to
            the caller (a `Transaction` or another `Method`). Assigned
            combinationally to the `data_out` attribute.

        Returns
        -------
        data_in : Record, out
            Data passed from the caller (a `Transaction` or another
            `Method`) to this `Method`.

        Examples
        --------
        .. highlight:: python
        .. code-block:: python

            m = Module()
            my_sum_method = Method(i = Layout([("arg1",8),("arg2",8)]))
            sum = Signal(16)
            with my_sum_method.body(m, out = sum) as data_in:
                m.d.comb += sum.eq(data_in.arg1 + data_in.arg2)
        """
        if self.defined:
            raise RuntimeError("Method already defined")
        try:
            m.d.comb += self.ready.eq(ready)
            m.d.comb += self.data_out.eq(out)
            with self.context():
                with m.If(self.run):
                    yield self.data_in
                m.d.comb += TransactionBase.comb
                TransactionBase.comb.clear()
        finally:
            self.defined = True

    def __call__(
        self, m: Module, arg: Optional[RecordDict] = None, enable: ValueLike = C(1), /, **kwargs: RecordDict
    ) -> Record:
        """Call a method.

        Methods can only be called from transaction and method bodies.
        Calling a `Method` marks, for the purpose of transaction scheduling,
        the dependency between the calling context and the called `Method`.
        It also connects the method's inputs to the parameters and the
        method's outputs to the return value.

        Parameters
        ----------
        m : Module
            Module in which operations on signals should be executed,
        arg : Value or dict of Values
            Call argument. Can be passed as a `Record` of the method's
            input layout or as a dictionary. Alternative syntax uses
            keyword arguments.
        enable : Value
            Configures the call as enabled in the current clock cycle.
            Disabled calls still lock the called method in transaction
            scheduling. Calls are by default enabled.
        **kwargs : Value or dict of Values
            Allows to pass method arguments using keyword argument
            syntax. Equivalent to passing a dict as the argument.

        Returns
        -------
        data_out : Record
            The result of the method call.

        Examples
        --------
        .. highlight:: python
        .. code-block:: python

            m = Module()
            with Transaction.body(m):
                ret = my_sum_method(m, arg1=2, arg2=3)

        Alternative syntax:

        .. highlight:: python
        .. code-block:: python

            with Transaction.body(m):
                ret = my_sum_method(m, {"arg1": 2, "arg2": 3})
        """
        enable_sig = Signal()
        arg_rec = Record.like(self.data_in)

        if arg is not None and kwargs:
            raise ValueError("Method call with both keyword arguments and legacy record argument")

        if arg is None:
            arg = kwargs

        m.d.comb += enable_sig.eq(enable)
        TransactionBase.comb += _connect_rec_with_possibly_dict(arg_rec, arg)
        TransactionBase.get().use_method(self, arg_rec, enable_sig)
        return self.data_out

    def __repr__(self) -> str:
        return "(method {})".format(self.name)

    def debug_signals(self) -> DebugSignals:
        return [self.ready, self.run, self.data_in, self.data_out]


def def_method(m: Module, method: Method, ready: ValueLike = C(1)):
    """Define a method.

    This decorator allows to define transactional methods in an
    elegant way using Python's `def` syntax. Internally, `def_method`
    uses `Method.body`.

    The decorated function should take one argument, which will be a
    record with input signals and return output values.
    The returned value can be either a record or a dictionary of outputs.

    Parameters
    ----------
    m: Module
        Module in which operations on signals should be executed.
    method: Method
        The method whose body is going to be defined.
    ready: Signal
        Signal to indicate if the method is ready to be run. By
        default it is `Const(1)`, so the method is always ready.
        Assigned combinationally to the `ready` attribute.

    Examples
    --------
    .. highlight:: python
    .. code-block:: python

        m = Module()
        my_sum_method = Method(i=[("arg1",8),("arg2",8)], o=[("res",8)])
        @def_method(m, my_sum_method)
        def _(data_in):
            return {"res": data_in.arg1 + data_in.arg2}
    """

    def decorator(func: Callable[[Record], Optional[RecordDict]]):
        out = Record.like(method.data_out)
        ret_out = None

        with method.body(m, ready=ready, out=out) as arg:
            ret_out = func(arg)

        if ret_out is not None:
            m.d.comb += _connect_rec_with_possibly_dict(out, ret_out)

    return decorator
