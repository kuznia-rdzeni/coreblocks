
from contextlib import contextmanager
from typing import Union, List
from amaranth import *
from ._utils import *

__all__ = [
    "TransactionManager", "TransactionContext", "TransactionModule",
    "Transaction", "Method"
]

class TransactionManager(Elaboratable):
    def __init__(self):
        self.transactions = {}
        self.methods = {}
        self.conflicts = []

    def add_conflict(self, end1 : Union['Transaction', 'Method'],
                           end2 : Union['Transaction', 'Method']) -> None:
        self.conflicts.append((end1, end2))

    def use_method(self, transaction : 'Transaction', method : 'Method', arg=C(0, 0)):
        assert transaction.manager is self and method.manager is self
        if not transaction in self.transactions:
            self.transactions[transaction] = []
        if not method in self.methods:
            self.methods[method] = []
        self.transactions[transaction].append(method)
        self.methods[method].append((transaction, arg))
        return method.data_out

    def _conflict_graph(self):
        def methodTrans(method):
            for transaction, _ in self.methods[method]:
                yield transaction

        def endTrans(end):
            if isinstance(end, Method):
                return methodTrans(end)
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
                for transaction2 in methodTrans(method):
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
            sched = Scheduler(len(cc))
            m.submodules += sched
            for k, transaction in enumerate(cc):
                methods = self.transactions[transaction]
                ready = Signal(len(methods))
                for n, method in enumerate(methods):
                    m.d.comb += ready[n].eq(method.ready)
                runnable = ready.all()
                m.d.comb += sched.requests[k].eq(transaction.request & runnable)
                m.d.comb += transaction.grant.eq(sched.grant[k] & sched.valid)

        for method, transactions in self.methods.items():
            granted = Signal(len(transactions))
            for n, (transaction, tdata) in enumerate(transactions):
                m.d.comb += granted[n].eq(transaction.grant)

                with m.If(transaction.grant):
                    m.d.comb += method.data_in.eq(tdata)
            runnable = granted.any()
            m.d.comb += method.run.eq(runnable)

        return m

class TransactionContext:
    stack : List[TransactionManager] = []

    def __init__(self, manager : TransactionManager):
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
    def __init__(self, module):
        Module.__init__(self)
        self.transactionManager = TransactionManager()
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
    current = None

    def __init__(self, *, request=C(1), manager : TransactionManager = None):
        if manager is None:
            manager = TransactionContext.get()
        self.request = request
        self.grant = Signal()
        self.manager = manager

    def __enter__(self):
        if self.__class__.current is not None:
            raise RuntimeError("Transaction inside transaction")
        self.__class__.current = self
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        self.__class__.current = None

    def add_conflict(self, end : Union['Transaction', 'Method']) -> None:
        self.manager.add_conflict(self, end)

    @classmethod
    def get(cls) -> 'Transaction':
        if cls.current is None:
            raise RuntimeError("No current transaction")
        return cls.current

class Method:
    def __init__(self, *, i=0, o=0, manager : TransactionManager = None):
        if manager is None:
            manager = TransactionContext.get()
        self.ready = Signal()
        self.run = Signal()
        self.manager = manager
        if isinstance(i, int):
            i = [('data', i)]
        self.data_in = Record(i)
        if isinstance(o, int):
            o = [('data', o)]
        self.data_out = Record(o)

    def add_conflict(self, end : Union['Transaction', 'Method']) -> None:
        self.manager.add_conflict(self, end)

    @contextmanager
    def when_called(self, m : Module, ready=C(1), ret=C(0, 0)):
        m.d.comb += self.ready.eq(ready)
        m.d.comb += self.data_out.eq(ret)
        with m.If(self.run):
            yield self.data_in

    def __call__(self, arg=C(0, 0)):
        trans = Transaction.get()
        return self.manager.use_method(trans, self, arg)


