from contextlib import contextmanager
from typing import Union, List
from types import MethodType
from amaranth import *
from ._utils import *

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
        ready = [method.ready for method in manager.transactions[transaction]]
        runnable = Cat(ready).all()
        conflicts = [ccl[j].grant for j in range(k) if ccl[j] in gr[transaction]]
        noconflict = ~Cat(conflicts).any()
        m.d.comb += transaction.grant.eq(transaction.request & runnable & noconflict)


def trivial_roundrobin_cc_scheduler(manager, m, gr, cc):
    sched = Scheduler(len(cc))
    m.submodules += sched
    for k, transaction in enumerate(cc):
        methods = manager.transactions[transaction]
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
        self.transactions = {}
        self.methods = {}
        self.methodargs = {}
        self.conflicts = []
        self.cc_scheduler = MethodType(cc_scheduler, self)

    def add_conflict(self, end1: Union["Transaction", "Method"], end2: Union["Transaction", "Method"]) -> None:
        self.conflicts.append((end1, end2))

    def use_method(self, transaction: "Transaction", method: "Method", arg=C(0, 0), enable=C(1)):
        assert transaction.manager is self and method.manager is self
        if (transaction, method) in self.methodargs:
            raise RuntimeError("Method can't be called twice from the same transaction")
        if transaction not in self.transactions:
            self.transactions[transaction] = []
        if method not in self.methods:
            self.methods[method] = []
        self.transactions[transaction].append(method)
        self.methods[method].append(transaction)
        self.methodargs[(transaction, method)] = (arg, enable)
        return method.data_out

    def _conflict_graph(self):
        def endTrans(end):
            if isinstance(end, Method):
                return self.methods[end]
            else:
                return [end]

        gr = {}

        def addEdge(transaction, transaction2):
            gr[transaction].add(transaction2)
            gr[transaction2].add(transaction)

        for transaction in self.transactions.keys():
            gr[transaction] = set()

        for transaction, methods in self.transactions.items():
            for method in methods:
                for transaction2 in self.methods[method]:
                    if transaction is not transaction2:
                        addEdge(transaction, transaction2)

        for (end1, end2) in self.conflicts:
            for transaction in endTrans(end1):
                for transaction2 in endTrans(end2):
                    addEdge(transaction, transaction2)

        return gr

    def elaborate(self, platform):
        m = Module()

        gr = self._conflict_graph()

        for cc in _graph_ccs(gr):
            self.cc_scheduler(m, gr, cc)

        for method, transactions in self.methods.items():
            granted = Signal(len(transactions))
            for n, transaction in enumerate(transactions):
                (tdata, enable) = self.methodargs[(transaction, method)]
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

    def __init__(self, module, manager: TransactionManager = None):
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

    A ``Transaction`` allows to simultaneously access multiple ``Method``s
    in a single clock cycle. It is granted by the ``TransactionManager``
    only when every ``Method`` it needs is ready, and no conflicting
    ``Transaction`` is already granted.

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

    def __init__(self, *, manager: TransactionManager = None):
        if manager is None:
            manager = TransactionContext.get()
        self.request = Signal()
        self.grant = Signal()
        self.manager = manager

    @contextmanager
    def context(self):
        if self.__class__.current is not None:
            raise RuntimeError("Transaction inside transaction")
        self.__class__.current = self
        try:
            yield self
        finally:
            self.__class__.current = None

    @contextmanager
    def body(self, m: Module, *, request=C(1)):
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
        self.manager.add_conflict(self, end)

    @classmethod
    def get(cls) -> "Transaction":
        if cls.current is None:
            raise RuntimeError("No current transaction")
        return cls.current


def _connect_rec_with_possibly_dict(dst, src):
    if isinstance(src, dict):
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
    else:
        return [dst.eq(src)]


class Method:
    """Transactional method.

    A ``Method`` serves to interface a module with external ``Transaction``s.
    It can be called by at most one ``Transaction`` in a given clock cycle.
    When a given ``Method`` is required by multiple ``Transaction``s
    simultenaously, at most one of them is granted by the
    ``TransactionManager``, and the rest of them must wait.
    Calling a ``Method`` always takes a single clock cycle.

    Data is combinatorially transferred between ``Method``s and
    ``Transaction``s using Amaranth ``Record``s. The transfer can take place
    in both directions at the same time: from ``Method`` to ``Transaction``
    (``data_out``) and from ``Transaction`` to ``Method`` (``data_in``).

    A module which defines a ``Method`` should use ``body`` to describe
    the method's effect on the module state.

    Parameters
    ----------
    i: int or record layout
        The format of ``data_in``.
        An ``int`` corresponds to a ``Record`` with a single ``data`` field.
    o: int or record layout
        The format of ``data_in``.
        An ``int`` corresponds to a ``Record`` with a single ``data`` field.
    manager: TransactionManager
        The ``TransactionManager`` controlling this ``Method``.
        If omitted, the manager is received from ``TransactionContext``.

    Attributes
    ----------
    ready: Signal, in
        Signals that the method is ready to run in the current cycle.
        Typically defined by calling ``body``.
    run: Signal, out
        Signals that the method is called in the current cycle by some
        ``Transaction``. Defined by the ``TransactionManager``.
    data_in: Record, out
        Contains the data passed to the ``Method`` by the calling
        ``Transaction``.
    data_out: Record, in
        Contains the data passed from the ``Method`` to the calling
        ``Transaction``. Typically defined by calling ``body``.
    """

    def __init__(self, *, i=0, o=0, manager: TransactionManager = None):
        if manager is None:
            manager = TransactionContext.get()
        self.ready = Signal()
        self.run = Signal()
        self.manager = manager
        self.data_in = Record(_coerce_layout(i))
        self.data_out = Record(_coerce_layout(o))

    def add_conflict(self, end: Union["Transaction", "Method"]) -> None:
        """Registers a conflict.

        The ``TransactionManager`` is informed that given ``Transaction``
        or ``Method`` cannot execute simultaneously with this ``Method``.
        Typical reason is using a common resource (register write
        or memory port).

        Parameters
        ----------
        end: Transaction or Method
            The conflicting ``Transaction`` or ``Method``
        """
        self.manager.add_conflict(self, end)

    @contextmanager
    def body(self, m: Module, *, ready=C(1), out=C(0, 0)):
        """Define method body

        The ``body`` function should be used to define body of
        a method. It use ``ready`` and ``ret`` signals provided by
        user to feed internal transactions logic and to pass this data
        to method users.

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
            the calling ``Transaction``. Assigned combinatorially to
            the ``data_out`` attribute.

        Returns
        -------
        data_in : Record, out
            Data passed from the calling ``Transaction`` to the ``Method``.

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
        m.d.comb += self.ready.eq(ready)
        m.d.comb += self.data_out.eq(out)
        with m.If(self.run):
            yield self.data_in

    def __call__(self, m: Module, arg=C(0, 0), enable=C(1)):
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

        trans = Transaction.get()
        return self.manager.use_method(trans, self, arg_rec, enable_sig)


def def_method(m: Module, method: Method, ready=C(1)):
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
