from collections import defaultdict
from contextlib import contextmanager
from typing import Union, List, Optional, Dict, Tuple, Set, Iterator
from types import MethodType
from amaranth import *
from ._utils import *
from .._typing import ValueLike

__all__ = [
    "TransactionManager",
    "TransactionContext",
    "TransactionModule",
    "Transaction",
    "Method",
    "eager_deterministic_cc_scheduler",
    "trivial_roundrobin_cc_scheduler",
    "def_method",
]


def eager_deterministic_cc_scheduler(manager, m, gr, cc):
    ccl = list(cc)
    for k, transaction in enumerate(ccl):
        ready = [method.ready for method in manager.methods_by_transaction[transaction]]
        runnable = Cat(ready).all()
        conflicts = [ccl[j].grant for j in range(k) if ccl[j] in gr[transaction]]
        noconflict = ~Cat(conflicts).any()
        m.d.comb += transaction.grant.eq(transaction.request & runnable & noconflict)


def trivial_roundrobin_cc_scheduler(manager, m, gr, cc):
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

    This module is responsible for granting ``Transaction``s and running
    ``Method``s. It takes care that two conflicting ``Transaction``s
    are never granted in the same clock cycle.
    """

    def __init__(self, cc_scheduler=eager_deterministic_cc_scheduler):
        self.transactions: List[Transaction] = []
        self.conflicts: List[Tuple[Transaction | Method, Transaction | Method]] = []
        self.cc_scheduler = MethodType(cc_scheduler, self)

    def add_transaction(self, transaction):
        self.transactions.append(transaction)

    def _conflict_graph(self):
        def endTrans(end):
            if isinstance(end, Method):
                return self.transactions_by_method[end]
            else:
                return [end]

        gr: Dict[Transaction, Set[Transaction]] = {}

        def addEdge(transaction, transaction2):
            gr[transaction].add(transaction2)
            gr[transaction2].add(transaction)

        for transaction in self.methods_by_transaction.keys():
            gr[transaction] = set()

        for transaction, methods in self.methods_by_transaction.items():
            for method in methods:
                for transaction2 in self.transactions_by_method[method]:
                    if transaction is not transaction2:
                        addEdge(transaction, transaction2)

        for (end1, end2) in self.conflicts:
            for transaction in endTrans(end1):
                for transaction2 in endTrans(end2):
                    addEdge(transaction, transaction2)

        return gr

    def _call_graph(self, transaction, method, arg, enable):
        if not method.defined:
            raise RuntimeError("Trying to use method which is not defined yet")
        if method in self.method_uses[transaction]:
            raise RuntimeError("Method can't be called twice from the same transaction")
        self.method_uses[transaction][method] = (arg, enable)
        self.methods_by_transaction[transaction].append(method)
        self.transactions_by_method[method].append(transaction)
        for end in method.conflicts:
            self.conflicts.append((method, end))
        for method, (arg, enable) in method.method_uses.items():
            self._call_graph(transaction, method, arg, enable)

    def elaborate(self, platform):

        self.methods_by_transaction = defaultdict(list)
        self.transactions_by_method = defaultdict(list)
        self.method_uses = defaultdict(dict)

        for transaction in self.transactions:
            for end in transaction.conflicts:
                self.conflicts.append((transaction, end))
            for method, (arg, enable) in transaction.method_uses.items():
                self._call_graph(transaction, method, arg, enable)

        gr = self._conflict_graph()

        m = Module()

        for cc in _graph_ccs(gr):
            self.cc_scheduler(m, gr, cc)

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


class TransactionContext:
    stack: List[TransactionManager] = []

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
    and can be used in definition of ``Method``s and ``Transaction``s.

    Parameters
    ----------
    module: Module
            The ``Module`` which should be wrapped to add support for
            transactions and methods.
    """

    def __init__(self, module: Module, manager: Optional[TransactionManager] = None):
        if manager is None:
            manager = TransactionManager()
        self.transactionManager = manager
        self.module = module

    def transactionContext(self) -> TransactionContext:
        return TransactionContext(self.transactionManager)

    def elaborate(self, platform):
        with self.transactionContext():
            for name in self.module._named_submodules:
                self.module._named_submodules[name] = Fragment.get(self.module._named_submodules[name], platform)
            for idx in range(len(self.module._anon_submodules)):
                self.module._anon_submodules[idx] = Fragment.get(self.module._anon_submodules[idx], platform)

        self.module.submodules += self.transactionManager

        return self.module


class Transaction:
    """Transaction.

    A ``Transaction`` represents a task which needs to be regularly done.
    Execution of a ``Transaction`` always lasts a single clock cycle.
    A ``Transaction`` signals readiness for execution by setting the
    ``request`` signal. If the conditions for its execution are met, it
    can be granted by the ``TransactionManager``.

    A ``Transaction`` can, as part of its execution, call a number of
    ``Method``s. A ``Transaction`` can be granted only if every ``Method``
    it runs is ready.

    A ``Transaction`` cannot execute concurrently with another, conflicting
    ``Transaction``. Conflicts between ``Transaction``s are either explicit
    or implicit. An explicit conflict is added using the ``add_conflict``
    method. Implicit conflicts arise between pairs of ``Transaction``s
    which use the same ``Method``.

    A module which defines a ``Transaction`` should use ``body`` to
    describe used methods and the transaction's effect on the module state.
    The used methods should be called inside the ``body``'s
    ``with`` block.

    Parameters
    ----------
    manager: TransactionManager
        The ``TransactionManager`` controlling this ``Transaction``.
        If omitted, the manager is received from ``TransactionContext``.

    Attributes
    ----------
    request: Signal, in
        Signals that the transaction wants to run. If omitted, the transaction
        is always ready. Defined in the constructor.
    grant: Signal, out
        Signals that the transaction is granted by the ``TransactionManager``,
        and all used methods are called.
    """

    current = None

    def __init__(self, *, manager: Optional[TransactionManager] = None):
        if manager is None:
            manager = TransactionContext.get()
        manager.add_transaction(self)
        self.request = Signal()
        self.grant = Signal()
        self.method_uses = dict()
        self.conflicts = []

    def use_method(self, method: "Method", arg, enable):
        if method in self.method_uses:
            raise RuntimeError("Method can't be called twice from the same transaction")
        self.method_uses[method] = (arg, enable)

    @contextmanager
    def context(self) -> Iterator["Transaction"]:
        if self.__class__.current is not None:
            raise RuntimeError("Transaction inside transaction")
        self.__class__.current = self
        try:
            yield self
        finally:
            self.__class__.current = None

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

    def add_conflict(self, end: Union["Transaction", "Method"]) -> None:
        """Registers a conflict.

        The ``TransactionManager`` is informed that given ``Transaction``
        or ``Method`` cannot execute simultaneously with this ``Transaction``.
        Typical reason is using a common resource (register write
        or memory port).

        Parameters
        ----------
        end: Transaction or Method
            The conflicting ``Transaction`` or ``Method``
        """
        self.conflicts.append(end)

    @classmethod
    def get(cls) -> "Transaction":
        if cls.current is None:
            raise RuntimeError("No current transaction")
        return cls.current


def _connect_rec_with_possibly_dict(dst, src):
    if not isinstance(src, dict):
        return [dst.eq(src)]

    if not isinstance(dst, Record):
        raise TypeError("Cannot connect a dict of signals to a non-record.")

    exprs = []
    for k, v in src.items():
        exprs += _connect_rec_with_possibly_dict(dst[k], v)

    # Make sure all fields of the record are specified in the dict.
    for field_name, _, _ in dst.layout:
        if field_name not in src:
            raise KeyError("Field {} is not specified in the dict.".format(field_name))

    return exprs


class Method:
    """Transactional method.

    A ``Method`` serves to interface a module with external ``Transaction``s
    or ``Method``s. It can be called by at most once in a given clock cycle.
    When a given ``Method`` is required by multiple ``Transaction``s
    (either directly, or indirectly via another ``Method``) simultenaously,
    at most one of them is granted by the ``TransactionManager``, and the rest
    of them must wait. Calling a ``Method`` always takes a single clock cycle.

    Data is combinatorially transferred between to and from ``Method``s
    using Amaranth ``Record``s. The transfer can take place in both directions
    at the same time: from the called ``Method`` to the caller (``data_out``)
    and from the caller to the called ``Method`` (``data_in``).

    A module which defines a ``Method`` should use ``body`` or ``def_method``
    to describe the method's effect on the module state.

    Parameters
    ----------
    i: int or record layout
        The format of ``data_in``.
        An ``int`` corresponds to a ``Record`` with a single ``data`` field.
    o: int or record layout
        The format of ``data_in``.
        An ``int`` corresponds to a ``Record`` with a single ``data`` field.

    Attributes
    ----------
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

    current = None

    def __init__(self, *, i: MethodLayout = 0, o: MethodLayout = 0, manager: Optional[TransactionManager] = None):
        self.ready = Signal()
        self.run = Signal()
        self.data_in = Record(_coerce_layout(i))
        self.data_out = Record(_coerce_layout(o))
        self.conflicts = []
        self.method_uses = dict()
        self.defined = False

    def add_conflict(self, end: Union["Transaction", "Method"]) -> None:
        """Registers a conflict.

        Record that that the given ``Transaction`` or ``Method`` cannot execute
        simultaneously with this ``Method``.  Typical reason is using a common
        resource (register write or memory port).

        Parameters
        ----------
        end: Transaction or Method
            The conflicting ``Transaction`` or ``Method``
        """
        self.conflicts.append(end)

    @contextmanager
    def body(self, m: Module, *, ready: ValueLike = C(1), out: ValueLike = C(0, 0)) -> Iterator[Record]:
        """Define method body

        The ``body`` function should be used to define body of
        a method. It uses the ``ready`` and ``ret`` signals provided by
        the user to feed internal transactions logic and to pass this data
        to method users. Inside the body, other ``Method``s can be called.

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

        Example
        -------
        ```
        m = Module()
        my_sum_method = Method(i = Layout([("arg1",8),("arg2",8)]))
        sum = Signal(16)
        with my_sum_method.body(m, out = sum) as data_in:
            m.d.comb += sum.eq(data_in.arg1 + data_in.arg2)
        ```
        """
        if self.defined:
            raise RuntimeError("Method already defined")
        if self.__class__.current is not None:
            raise RuntimeError("Method body inside method body")
        self.__class__.current = self
        try:
            m.d.comb += self.ready.eq(ready)
            m.d.comb += self.data_out.eq(out)
            with m.If(self.run):
                yield self.data_in
        finally:
            self.__class__.current = None
            self.defined = True

    def use_method(self, method: "Method", arg, enable):
        if method in self.method_uses:
            raise RuntimeError("Method can't be called twice from the same transaction")
        self.method_uses[method] = (arg, enable)

    def __call__(self, m: Module, arg: ValueLike = C(0, 0), enable: ValueLike = C(1)) -> Record:
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
        if Method.current is not None:
            Method.current.use_method(self, arg_rec, enable_sig)
        else:
            Transaction.get().use_method(self, arg_rec, enable_sig)
        return self.data_out


def def_method(m: Module, method: Method, ready: ValueLike = C(1)):
    """Define a method.

    This decorator allows to define transactional methods in more
    elegant way using Python's ``def`` syntax.

    The decorated function should take one argument, which will be a
    record with input signals and return output values.
    The returned value can be either a record or a dictionary of outputs.

    Parameters
    ----------
    m : Module
        Module in which operations on signals should be executed.
    method : Method
        The method whose body is going to be defined.
    ready : Signal
        Signal to indicate if the method is ready to be run. By
        default it is ``Const(1)``, so the method is always ready.
        Assigned combinatorially to the ``ready`` attribute.

    Example
    -------
    ```
    m = Module()
    my_sum_method = Method(i=[("arg1",8),("arg2",8)], o=8)
    @def_method(m, my_sum_method)
    def _(data_in):
        return data_in.arg1 + data_in.arg2
    ```
    """

    def decorator(func):
        out = Record.like(method.data_out)
        ret_out = None

        with method.body(m, ready=ready, out=out) as arg:
            ret_out = func(arg)

        if ret_out is not None:
            m.d.comb += _connect_rec_with_possibly_dict(out, ret_out)

    return decorator
