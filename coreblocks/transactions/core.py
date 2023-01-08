from collections import defaultdict
from contextlib import contextmanager
from enum import Enum, auto
from typing import Callable, ClassVar, Mapping, TypeAlias, Union, Optional, Tuple, Iterator
from types import MethodType
from graphlib import TopologicalSorter
from typing_extensions import Self
from amaranth import *
from amaranth import tracer
from amaranth.hdl.ast import Assign
from ._utils import *
from ..utils._typing import ValueLike, DebugSignals
from .graph import OwnershipGraph

__all__ = [
    "ConflictPriority",
    "TransactionManager",
    "TransactionContext",
    "TransactionModule",
    "Transaction",
    "Method",
    "eager_deterministic_cc_scheduler",
    "trivial_roundrobin_cc_scheduler",
    "def_method",
]


ConflictGraph: TypeAlias = Graph["Transaction"]
ConflictGraphCC: TypeAlias = GraphCC["Transaction"]
PriorityOrder: TypeAlias = dict["Transaction", int]
TransactionScheduler: TypeAlias = Callable[
    ["TransactionManager", Module, ConflictGraph, ConflictGraphCC, PriorityOrder], None
]
RecordDict: TypeAlias = ValueLike | Mapping[str, "RecordDict"]


class ConflictPriority(Enum):
    UNDEFINED = auto()
    LEFT = auto()
    RIGHT = auto()


def eager_deterministic_cc_scheduler(
    manager: "TransactionManager", m: Module, gr: ConflictGraph, cc: ConflictGraphCC, porder: PriorityOrder
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
    gr : ConflictGraph
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
    manager: "TransactionManager", m: Module, gr: ConflictGraph, cc: ConflictGraphCC, porder: PriorityOrder
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
    gr : ConflictGraph
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

    This module is responsible for granting ``Transaction``\\s and running
    ``Method``\\s. It takes care that two conflicting ``Transaction``\\s
    are never granted in the same clock cycle.
    """

    def __init__(self, cc_scheduler: TransactionScheduler = eager_deterministic_cc_scheduler):
        self.transactions: list[Transaction] = []
        self.conflicts: list[Tuple[Transaction | Method, Transaction | Method, ConflictPriority]] = []
        self.cc_scheduler = MethodType(cc_scheduler, self)

    def add_transaction(self, transaction: "Transaction"):
        self.transactions.append(transaction)

    def _conflict_graph(self) -> Tuple[ConflictGraph, PriorityOrder]:
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
        ----------
        gr : ConflictGraph
            Graph of conflicts between transactions, where vertices are transactions and edges are conflicts.
        porder : PriorityOrder
            Linear ordering of transactions which is consistent with priority constraints.
        """

        def end_trans(end: Transaction | Method) -> list[Transaction]:
            if isinstance(end, Method):
                return self.transactions_by_method[end]
            else:
                return [end]

        gr: ConflictGraph = {}  # Conflict graph
        pgr: ConflictGraph = {}  # Priority graph

        def add_edge(transaction: Transaction, transaction2: Transaction, priority: ConflictPriority):
            gr[transaction].add(transaction2)
            gr[transaction2].add(transaction)
            match priority:
                case ConflictPriority.LEFT:
                    pgr[transaction2].add(transaction)
                case ConflictPriority.RIGHT:
                    pgr[transaction].add(transaction2)

        for transaction in self.transactions:
            gr[transaction] = set()
            pgr[transaction] = set()

        for transaction, methods in self.methods_by_transaction.items():
            for method in methods:
                if method.nonexclusive:
                    continue
                for transaction2 in self.transactions_by_method[method]:
                    if transaction is not transaction2:
                        add_edge(transaction, transaction2, ConflictPriority.UNDEFINED)

        for (end1, end2, priority) in self.conflicts:
            for transaction in end_trans(end1):
                for transaction2 in end_trans(end2):
                    add_edge(transaction, transaction2, priority)

        porder: PriorityOrder = {}

        for (k, transaction) in enumerate(TopologicalSorter(pgr).static_order()):
            porder[transaction] = k

        return gr, porder

    def _call_graph(self, transaction: "Transaction", method: "Method", arg: ValueLike, enable: ValueLike):
        if not method.defined:
            raise RuntimeError("Trying to use method which is not defined yet")
        if method in self.method_uses[transaction]:
            raise RuntimeError("Method can't be called twice from the same transaction")
        self.method_uses[transaction][method] = (arg, enable)
        self.methods_by_transaction[transaction].append(method)
        self.transactions_by_method[method].append(transaction)
        for end in method.conflicts:
            self.conflicts.append((method, end[0], end[1]))
        for method, (arg, enable) in method.method_uses.items():
            self._call_graph(transaction, method, arg, enable)

    def elaborate(self, platform):

        self.methods_by_transaction = defaultdict[Transaction, list[Method]](list)
        self.transactions_by_method = defaultdict[Method, list[Transaction]](list)
        self.method_uses = defaultdict[Transaction, dict[Method, Tuple[ValueLike, ValueLike]]](dict)

        for transaction in self.transactions:
            for end in transaction.conflicts:
                self.conflicts.append((transaction, end[0], end[1]))
            for method, (arg, enable) in transaction.method_uses.items():
                self._call_graph(transaction, method, arg, enable)

        gr, porder = self._conflict_graph()

        m = Module()

        for cc in _graph_ccs(gr):
            self.cc_scheduler(m, gr, cc, porder)

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
            graph.insert_node(method)
            for transaction in transactions:
                graph.insert_node(transaction)
                graph.insert_edge(method, transaction)

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
    ``TransactionModule`` is used as wrapper on ``Module`` class,
    which add support for transaction to the ``Module``. It creates a
    ``TransactionManager`` which will handle transaction scheduling
    and can be used in definition of ``Method``\\s and ``Transaction``\\s.
    """

    def __init__(self, module: Module, manager: Optional[TransactionManager] = None):
        """
        Parameters
        ----------
        module: Module
                The ``Module`` which should be wrapped to add support for
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


class TransactionBase:
    current: ClassVar[Optional["TransactionBase"]] = None

    def __init__(self):
        self.method_uses: dict[Method, Tuple[ValueLike, ValueLike]] = dict()
        self.conflicts: list[Tuple[Transaction | Method, ConflictPriority]] = []

    def add_conflict(
        self, end: Union["Transaction", "Method"], priority: ConflictPriority = ConflictPriority.UNDEFINED
    ) -> None:
        """Registers a conflict.

        Record that that the given ``Transaction`` or ``Method`` cannot execute
        simultaneously with this ``Method``.  Typical reason is using a common
        resource (register write or memory port).

        Parameters
        ----------
        end: Transaction or Method
            The conflicting ``Transaction`` or ``Method``
        priority: ConflictPriority, optional
            Is one of conflicting ``Transaction``\\s or ``Method``\\s prioritized?
            Defaults to undefined priority relation.
        """
        self.conflicts.append((end, priority))

    def use_method(self, method: "Method", arg: ValueLike, enable: ValueLike):
        if method in self.method_uses:
            raise RuntimeError("Method can't be called twice from the same transaction")
        self.method_uses[method] = (arg, enable)

    @contextmanager
    def context(self) -> Iterator[Self]:
        if TransactionBase.current is not None:
            raise RuntimeError("Body inside body")
        TransactionBase.current = self
        try:
            yield self
        finally:
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

    A ``Transaction`` represents a task which needs to be regularly done.
    Execution of a ``Transaction`` always lasts a single clock cycle.
    A ``Transaction`` signals readiness for execution by setting the
    ``request`` signal. If the conditions for its execution are met, it
    can be granted by the ``TransactionManager``.

    A ``Transaction`` can, as part of its execution, call a number of
    ``Method``\\s. A ``Transaction`` can be granted only if every ``Method``
    it runs is ready.

    A ``Transaction`` cannot execute concurrently with another, conflicting
    ``Transaction``. Conflicts between ``Transaction``\\s are either explicit
    or implicit. An explicit conflict is added using the ``add_conflict``
    method. Implicit conflicts arise between pairs of ``Transaction``\\s
    which use the same ``Method``.

    A module which defines a ``Transaction`` should use ``body`` to
    describe used methods and the transaction's effect on the module state.
    The used methods should be called inside the ``body``'s
    ``with`` block.

    Attributes
    ----------
    name: str
        Name of this ``Transaction``.
    request: Signal, in
        Signals that the transaction wants to run. If omitted, the transaction
        is always ready. Defined in the constructor.
    grant: Signal, out
        Signals that the transaction is granted by the ``TransactionManager``,
        and all used methods are called.
    """

    def __init__(self, *, name: Optional[str] = None, manager: Optional[TransactionManager] = None):
        """
        Parameters
        ----------
        name: str or None
            Name hint for this ``Transaction``. If ``None`` (default) the name is
            inferred from the variable name this ``Transaction`` is assigned to.
            If the ``Transaction`` was not assigned, the name is inferred from
            the class name where the ``Transaction`` was constructed.
        manager: TransactionManager
            The ``TransactionManager`` controlling this ``Transaction``.
            If omitted, the manager is received from ``TransactionContext``.
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
        """Defines the ``Transaction`` body.

        This context manager allows to conveniently define the actions
        performed by a ``Transaction`` when it's granted. Each assignment
        added to a domain under ``body`` is guarded by the ``grant`` signal.
        ``Method`` calls can be performed under ``body``.

        Parameters
        ----------
        m: Module
            The module where the ``Transaction`` is defined.
        request: Signal
            Indicates that the ``Transaction`` wants to be executed. By
            default it is ``Const(1)``, so it wants to be executed in
            every clock cycle.
        """
        m.d.comb += self.request.eq(request)
        with self.context():
            with m.If(self.grant):
                yield self

    def __repr__(self) -> str:
        return "(transaction {})".format(self.name)

    def debug_signals(self) -> DebugSignals:
        return [self.request, self.grant]


def _connect_rec_with_possibly_dict(dst: Value | Record, src: RecordDict) -> list[Assign]:
    if not isinstance(src, dict):
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

    A ``Method`` serves to interface a module with external ``Transaction``\\s
    or ``Method``\\s. It can be called by at most once in a given clock cycle.
    When a given ``Method`` is required by multiple ``Transaction``\\s
    (either directly, or indirectly via another ``Method``) simultenaously,
    at most one of them is granted by the ``TransactionManager``, and the rest
    of them must wait. (Non-exclusive methods are an exception to this
    behavior.) Calling a ``Method`` always takes a single clock cycle.

    Data is combinatorially transferred between to and from ``Method``\\s
    using Amaranth ``Record``\\s. The transfer can take place in both directions
    at the same time: from the called ``Method`` to the caller (``data_out``)
    and from the caller to the called ``Method`` (``data_in``).

    A module which defines a ``Method`` should use ``body`` or ``def_method``
    to describe the method's effect on the module state.

    Attributes
    ----------
    name: str
        Name of this ``Method``.
    ready: Signal, in
        Signals that the method is ready to run in the current cycle.
        Typically defined by calling ``body``.
    run: Signal, out
        Signals that the method is called in the current cycle by some
        ``Transaction``. Defined by the ``TransactionManager``.
    data_in: Record, out
        Contains the data passed to the ``Method`` by the caller
        (a ``Transaction`` or another ``Method``).
    data_out: Record, in
        Contains the data passed from the ``Method`` to the caller
        (a ``Transaction`` or another ``Method``). Typically defined by
        calling ``body``.
    """

    def __init__(
        self, *, name: Optional[str] = None, i: MethodLayout = 0, o: MethodLayout = 0, nonexclusive: bool = False
    ):
        """
        Parameters
        ----------
        name: str or None
            Name hint for this ``Method``. If ``None`` (default) the name is
            inferred from the variable name this ``Method`` is assigned to.
        i: int or record layout
            The format of ``data_in``.
            An ``int`` corresponds to a ``Record`` with a single ``data`` field.
        o: int or record layout
            The format of ``data_in``.
            An ``int`` corresponds to a ``Record`` with a single ``data`` field.
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
        self.data_in = Record(_coerce_layout(i))
        self.data_out = Record(_coerce_layout(o))
        self.defined = False
        self.nonexclusive = nonexclusive
        if nonexclusive:
            assert len(self.data_in) == 0

    @staticmethod
    def like(other: "Method", *, name: Optional[str] = None) -> "Method":
        """Constructs a new ``Method`` based on another.

        The returned ``Method`` has the same input/output data layouts as the
        ``other`` ``Method``.

        Parameters
        ----------
        other : Method
            The ``Method`` which serves as a blueprint for the new ``Method``.
        name : str, optional
            Name of the new ``Method``.

        Returns
        -------
        Method
            The freshly constructed ``Method``.
        """
        return Method(name=name, i=other.data_in.layout, o=other.data_out.layout)

    def proxy(self, m: Module, method: "Method"):
        """Define as a proxy for another method.

        The calls to this method will be forwarded to ``method``.

        Parameters
        ----------
        m : Module
            Module in which operations on signals should be executed,
            ``proxy`` uses the combinational domain only.
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

        The ``body`` function should be used to define body of
        a method. It uses the ``ready`` and ``ret`` signals provided by
        the user to feed internal transactions logic and to pass this data
        to method users. Inside the body, other ``Method`` s can be called.

        Parameters
        ----------
        m : Module
            Module in which operations on signals should be executed,
            ``body`` uses the combinational domain only.
        ready : Signal, in
            Signal to indicate if the method is ready to be run. By
            default it is ``Const(1)``, so the method is always ready.
            Assigned combinatorially to the ``ready`` attribute.
        out : Record, in
            Data generated by the ``Method``, which will be passed to
            the caller (a ``Transaction`` or another ``Method``). Assigned
            combinatorially to the ``data_out`` attribute.

        Returns
        -------
        data_in : Record, out
            Data passed from the caller (a ``Transaction`` or another
            ``Method``) to this ``Method``.

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
        finally:
            self.defined = True

    def __call__(self, m: Module, arg: RecordDict = C(0, 0), enable: ValueLike = C(1)) -> Record:
        enable_sig = Signal()
        arg_rec = Record.like(self.data_in)

        # TODO: These connections should be moved from here.
        # This function is called under Transaction context, so
        # every connection we make here is unnecessarily multiplexed
        # by transaction.grant signal. Thus, it adds superfluous
        # complexity to the circuit. One of the solutions would be
        # to temporarily save the connections and add them to the
        # combinatorial domain at a better moment.
        m.d.comb += enable_sig.eq(enable)
        m.d.comb += _connect_rec_with_possibly_dict(arg_rec, arg)
        TransactionBase.get().use_method(self, arg_rec, enable_sig)
        return self.data_out

    def __repr__(self) -> str:
        return "(method {})".format(self.name)

    def debug_signals(self) -> DebugSignals:
        return [self.ready, self.run, self.data_in, self.data_out]


def def_method(m: Module, method: Method, ready: ValueLike = C(1)):
    """Define a method.

    This decorator allows to define transactional methods in more
    elegant way using Python's ``def`` syntax.

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
        default it is ``Const(1)``, so the method is always ready.
        Assigned combinatorially to the ``ready`` attribute.

    Examples
    --------
    .. highlight:: python
    .. code-block:: python

        m = Module()
        my_sum_method = Method(i=[("arg1",8),("arg2",8)], o=8)
        @def_method(m, my_sum_method)
        def _(data_in):
            return data_in.arg1 + data_in.arg2
    """

    def decorator(func: Callable[[Record], Optional[RecordDict]]):
        out = Record.like(method.data_out)
        ret_out = None

        with method.body(m, ready=ready, out=out) as arg:
            ret_out = func(arg)

        if ret_out is not None:
            m.d.comb += _connect_rec_with_possibly_dict(out, ret_out)

    return decorator
