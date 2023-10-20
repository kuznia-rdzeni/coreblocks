from collections import defaultdict, deque
from collections.abc import Sequence, Iterable, Callable, Mapping, Iterator
from contextlib import contextmanager
from enum import Enum, auto
from typing import (
    ClassVar,
    NoReturn,
    TypeAlias,
    TypedDict,
    Union,
    Optional,
    Tuple,
    TypeVar,
    Protocol,
    runtime_checkable,
)
from graphlib import TopologicalSorter
from typing_extensions import Self
from amaranth import *
from amaranth import tracer
from itertools import count, chain, filterfalse, product
from amaranth.hdl.dsl import FSM, _ModuleBuilderDomain

from coreblocks.utils import AssignType, assign, ModuleConnector
from coreblocks.utils.utils import OneHotSwitchDynamic
from ._utils import *
from coreblocks.utils import silence_mustuse
from coreblocks.utils._typing import ValueLike, SignalBundle, HasElaborate, SwitchKey, ModuleLike
from .graph import Owned, OwnershipGraph, Direction

__all__ = [
    "MethodLayout",
    "Priority",
    "TModule",
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
TransactionScheduler: TypeAlias = Callable[["MethodMap", TransactionGraph, TransactionGraphCC, PriorityOrder], Module]
RecordDict: TypeAlias = ValueLike | Mapping[str, "RecordDict"]
TransactionOrMethod: TypeAlias = Union["Transaction", "Method"]
TransactionOrMethodBound = TypeVar("TransactionOrMethodBound", "Transaction", "Method")


class Priority(Enum):
    #: Conflicting transactions/methods don't have a priority order.
    UNDEFINED = auto()
    #: Left transaction/method is prioritized over the right one.
    LEFT = auto()
    #: Right transaction/method is prioritized over the left one.
    RIGHT = auto()


class RelationBase(TypedDict):
    end: TransactionOrMethod
    priority: Priority
    conflict: bool


class Relation(RelationBase):
    start: TransactionOrMethod


class MethodMap:
    def __init__(self, transactions: Iterable["Transaction"]):
        self.methods_by_transaction = dict[Transaction, list[Method]]()
        self.transactions_by_method = defaultdict[Method, list[Transaction]](list)

        def rec(transaction: Transaction, source: TransactionBase):
            for method in source.method_uses.keys():
                if not method.defined:
                    raise RuntimeError(f"Trying to use method '{method.name}' which is not defined yet")
                if method in self.methods_by_transaction[transaction]:
                    raise RuntimeError(f"Method '{method.name}' can't be called twice from the same transaction")
                self.methods_by_transaction[transaction].append(method)
                self.transactions_by_method[method].append(transaction)
                rec(transaction, method)

        for transaction in transactions:
            self.methods_by_transaction[transaction] = []
            rec(transaction, transaction)

    def transactions_for(self, elem: TransactionOrMethod) -> Iterable["Transaction"]:
        if isinstance(elem, Transaction):
            return [elem]
        else:
            return self.transactions_by_method[elem]

    @property
    def methods(self) -> Iterable["Method"]:
        return self.transactions_by_method.keys()

    @property
    def transactions(self) -> Iterable["Transaction"]:
        return self.methods_by_transaction.keys()

    @property
    def methods_and_transactions(self) -> Iterable[TransactionOrMethod]:
        return chain(self.methods, self.transactions)


def eager_deterministic_cc_scheduler(
    method_map: MethodMap, gr: TransactionGraph, cc: TransactionGraphCC, porder: PriorityOrder
) -> Module:
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
    gr : TransactionGraph
        Graph of conflicts between transactions, where vertices are transactions and edges are conflicts.
    cc : Set[Transaction]
        Connected components of the graph `gr` for which scheduler
        should be generated.
    porder : PriorityOrder
        Linear ordering of transactions which is consistent with priority constraints.
    """
    m = Module()
    ccl = list(cc)
    ccl.sort(key=lambda transaction: porder[transaction])
    for k, transaction in enumerate(ccl):
        ready = [method.ready for method in method_map.methods_by_transaction[transaction]]
        runnable = Cat(ready).all()
        conflicts = [ccl[j].grant for j in range(k) if ccl[j] in gr[transaction]]
        noconflict = ~Cat(conflicts).any()
        m.d.comb += transaction.grant.eq(transaction.request & runnable & noconflict)
    return m


def trivial_roundrobin_cc_scheduler(
    method_map: MethodMap, gr: TransactionGraph, cc: TransactionGraphCC, porder: PriorityOrder
) -> Module:
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
    gr : TransactionGraph
        Graph of conflicts between transactions, where vertices are transactions and edges are conflicts.
    cc : Set[Transaction]
        Connected components of the graph `gr` for which scheduler
        should be generated.
    porder : PriorityOrder
        Linear ordering of transactions which is consistent with priority constraints.
    """
    m = Module()
    sched = Scheduler(len(cc))
    m.submodules.scheduler = sched
    for k, transaction in enumerate(cc):
        methods = method_map.methods_by_transaction[transaction]
        ready = Signal(len(methods))
        for n, method in enumerate(methods):
            m.d.comb += ready[n].eq(method.ready)
        runnable = ready.all()
        m.d.comb += sched.requests[k].eq(transaction.request & runnable)
        m.d.comb += transaction.grant.eq(sched.grant[k] & sched.valid)
    return m


class TransactionManager(Elaboratable):
    """Transaction manager

    This module is responsible for granting `Transaction`\\s and running
    `Method`\\s. It takes care that two conflicting `Transaction`\\s
    are never granted in the same clock cycle.
    """

    def __init__(self, cc_scheduler: TransactionScheduler = eager_deterministic_cc_scheduler):
        self.transactions: list[Transaction] = []
        self.cc_scheduler = cc_scheduler

    def add_transaction(self, transaction: "Transaction"):
        self.transactions.append(transaction)

    @staticmethod
    def _conflict_graph(method_map: MethodMap) -> Tuple[TransactionGraph, TransactionGraph, PriorityOrder]:
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

        for transaction in method_map.transactions:
            cgr[transaction] = set()
            pgr[transaction] = set()
            rgr[transaction] = set()

        for method in method_map.methods:
            if method.nonexclusive:
                continue
            for transaction1 in method_map.transactions_for(method):
                for transaction2 in method_map.transactions_for(method):
                    if transaction1 is not transaction2:
                        add_edge(transaction1, transaction2, Priority.UNDEFINED, True)

        relations = [
            Relation(**relation, start=elem)
            for elem in method_map.methods_and_transactions
            for relation in elem.relations
        ]

        for relation in relations:
            start = relation["start"]
            end = relation["end"]
            if not relation["conflict"]:  # relation added with schedule_before
                if end.def_order < start.def_order:
                    raise RuntimeError(f"{start.name!r} scheduled before {end.name!r}, but defined afterwards")

            for trans_start in method_map.transactions_for(start):
                for trans_end in method_map.transactions_for(end):
                    add_edge(trans_start, trans_end, relation["priority"], relation["conflict"])

        porder: PriorityOrder = {}

        for k, transaction in enumerate(TopologicalSorter(pgr).static_order()):
            porder[transaction] = k

        return cgr, rgr, porder

    @staticmethod
    def _method_enables(method_map: MethodMap) -> Mapping["Transaction", Mapping["Method", ValueLike]]:
        method_enables = defaultdict[Transaction, dict[Method, ValueLike]](dict)
        enables: list[ValueLike] = []

        def rec(transaction: Transaction, source: TransactionOrMethod):
            for method, (_, enable) in source.method_uses.items():
                enables.append(enable)
                rec(transaction, method)
                method_enables[transaction][method] = Cat(*enables).all()
                enables.pop()

        for transaction in method_map.transactions:
            rec(transaction, transaction)

        return method_enables

    @staticmethod
    def _method_calls(
        m: Module, method_map: MethodMap
    ) -> tuple[Mapping["Method", Sequence[ValueLike]], Mapping["Method", Sequence[ValueLike]]]:
        args = defaultdict[Method, list[ValueLike]](list)
        runs = defaultdict[Method, list[ValueLike]](list)

        for source in method_map.methods_and_transactions:
            if isinstance(source, Method):
                run_val = Cat(transaction.grant for transaction in method_map.transactions_by_method[source]).any()
                run = Signal()
                m.d.comb += run.eq(run_val)
            else:
                run = source.grant
            for method, (arg, _) in source.method_uses.items():
                args[method].append(arg)
                runs[method].append(run)

        return (args, runs)

    def _simultaneous(self):
        method_map = MethodMap(self.transactions)

        # remove orderings between simultaneous methods/transactions
        # TODO: can it be done after transitivity, possibly catching more cases?
        for elem in method_map.methods_and_transactions:
            all_sims = frozenset(elem.simultaneous_list)
            elem.relations = list(
                filterfalse(
                    lambda relation: not relation["conflict"]
                    and relation["priority"] != Priority.UNDEFINED
                    and relation["end"] in all_sims,
                    elem.relations,
                )
            )

        # step 1: simultaneous and independent sets generation
        independents = defaultdict[Transaction, set[Transaction]](set)

        for elem in method_map.methods_and_transactions:
            indeps = frozenset[Transaction]().union(
                *(frozenset(method_map.transactions_for(ind)) for ind in chain([elem], elem.independent_list))
            )
            for transaction1, transaction2 in product(indeps, indeps):
                independents[transaction1].add(transaction2)

        simultaneous = set[frozenset[Transaction]]()

        for elem in method_map.methods_and_transactions:
            for sim_elem in elem.simultaneous_list:
                for tr1, tr2 in product(method_map.transactions_for(elem), method_map.transactions_for(sim_elem)):
                    if tr1 in independents[tr2]:
                        raise RuntimeError(
                            f"Unsatisfiable simultaneity constraints for '{elem.name}' and '{sim_elem.name}'"
                        )
                    simultaneous.add(frozenset({tr1, tr2}))

        # step 2: transitivity computation
        tr_simultaneous = set[frozenset[Transaction]]()

        def conflicting(group: frozenset[Transaction]):
            return any(tr1 != tr2 and tr1 in independents[tr2] for tr1 in group for tr2 in group)

        q = deque[frozenset[Transaction]](simultaneous)

        while q:
            new_group = q.popleft()
            if new_group in tr_simultaneous or conflicting(new_group):
                continue
            q.extend(new_group | other_group for other_group in simultaneous if new_group & other_group)
            tr_simultaneous.add(new_group)

        # step 3: maximal group selection
        def maximal(group: frozenset[Transaction]):
            return not any(group.issubset(group2) and group != group2 for group2 in tr_simultaneous)

        final_simultaneous = set(filter(maximal, tr_simultaneous))

        # step 4: convert transactions to methods
        joined_transactions = set[Transaction]().union(*final_simultaneous)

        self.transactions = list(filter(lambda t: t not in joined_transactions, self.transactions))
        methods = dict[Transaction, Method]()

        for transaction in joined_transactions:
            # TODO: some simpler way?
            method = Method(name=transaction.name)
            method.owner = transaction.owner
            method.ready = transaction.request
            method.run = transaction.grant
            method.defined = transaction.defined
            method.method_uses = transaction.method_uses
            method.relations = transaction.relations
            method.def_order = transaction.def_order
            methods[transaction] = method

        for elem in method_map.methods_and_transactions:
            # I guess method/transaction unification is really needed
            for relation in elem.relations:
                if relation["end"] in methods:
                    relation["end"] = methods[relation["end"]]

        # step 5: construct merged transactions
        m = TModule()
        m._MustUse__silence = True  # type: ignore

        for group in final_simultaneous:
            name = "_".join([t.name for t in group])
            with Transaction(manager=self, name=name).body(m):
                for transaction in group:
                    methods[transaction](m)

        return m

    def elaborate(self, platform):
        # In the following, various problems in the transaction set-up are detected.
        # The exception triggers an unused Elaboratable warning.
        with silence_mustuse(self):
            merge_manager = self._simultaneous()

            method_map = MethodMap(self.transactions)
            cgr, rgr, porder = TransactionManager._conflict_graph(method_map)

        m = Module()
        m.submodules.merge_manager = merge_manager

        m.submodules._transactron_schedulers = ModuleConnector(
            *[self.cc_scheduler(method_map, cgr, cc, porder) for cc in _graph_ccs(rgr)]
        )

        method_enables = self._method_enables(method_map)

        for method, transactions in method_map.transactions_by_method.items():
            granted = Cat(transaction.grant & method_enables[transaction][method] for transaction in transactions)
            m.d.comb += method.run.eq(granted.any())

        (method_args, method_runs) = self._method_calls(m, method_map)

        for method in method_map.methods:
            if len(method_args[method]) == 1:
                m.d.comb += method.data_in.eq(method_args[method][0])
            else:
                if method.single_caller:
                    raise RuntimeError(f"Single-caller method '{method.name}' called more than once")

                runs = Cat(method_runs[method])
                for i in OneHotSwitchDynamic(m, runs):
                    m.d.comb += method.data_in.eq(method_args[method][i])

        return m

    def visual_graph(self, fragment):
        graph = OwnershipGraph(fragment)
        method_map = MethodMap(self.transactions)
        for method, transactions in method_map.transactions_by_method.items():
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

    def debug_signals(self) -> SignalBundle:
        method_map = MethodMap(self.transactions)
        cgr, _, _ = TransactionManager._conflict_graph(method_map)

        def transaction_debug(t: Transaction):
            return (
                [t.request, t.grant]
                + [m.ready for m in method_map.methods_by_transaction[t]]
                + [t2.grant for t2 in cgr[t]]
            )

        def method_debug(m: Method):
            return [m.ready, m.run, {t.name: transaction_debug(t) for t in method_map.transactions_by_method[m]}]

        return {
            "transactions": {t.name: transaction_debug(t) for t in method_map.transactions},
            "methods": {m.owned_name: method_debug(m) for m in method_map.methods},
        }


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
    `TransactionModule` is used as wrapper on `Elaboratable` classes,
    which adds support for transactions. It creates a
    `TransactionManager` which will handle transaction scheduling
    and can be used in definition of `Method`\\s and `Transaction`\\s.
    """

    def __init__(self, elaboratable: HasElaborate, manager: Optional[TransactionManager] = None):
        """
        Parameters
        ----------
        elaboratable: HasElaborate
                The `Elaboratable` which should be wrapped to add support for
                transactions and methods.
        """
        if manager is None:
            manager = TransactionManager()
        self.transactionManager = manager
        self.elaboratable = elaboratable

    def transaction_context(self) -> TransactionContext:
        return TransactionContext(self.transactionManager)

    def elaborate(self, platform):
        with silence_mustuse(self.transactionManager):
            with self.transaction_context():
                elaboratable = Fragment.get(self.elaboratable, platform)

        m = Module()

        m.submodules.main_module = elaboratable
        m.submodules.transactionManager = self.transactionManager

        return m


class _AvoidingModuleBuilderDomains:
    _m: "TModule"

    def __init__(self, m: "TModule"):
        object.__setattr__(self, "_m", m)

    def __getattr__(self, name: str) -> _ModuleBuilderDomain:
        if name == "av_comb":
            return self._m.avoiding_module.d["comb"]
        elif name == "top_comb":
            return self._m.top_module.d["comb"]
        else:
            return self._m.main_module.d[name]

    def __getitem__(self, name: str) -> _ModuleBuilderDomain:
        return self.__getattr__(name)

    def __setattr__(self, name: str, value):
        if not isinstance(value, _ModuleBuilderDomain):
            raise AttributeError(f"Cannot assign 'd.{name}' attribute; did you mean 'd.{name} +='?")

    def __setitem__(self, name: str, value):
        return self.__setattr__(name, value)


class TModule(ModuleLike, Elaboratable):
    """Extended Amaranth module for use with transactions.

    It includes three different combinational domains:

    * `comb` domain, works like the `comb` domain in plain Amaranth modules.
      Statements in `comb` are guarded by every condition, including
      `AvoidedIf`. This means they are guarded by transaction and method
      bodies: they don't execute if the given transaction/method is not run.
    * `av_comb` is guarded by all conditions except `AvoidedIf`. This means
      they are not guarded by transaction and method bodies. This allows to
      reduce the amount of useless multplexers due to transaction use, while
      still allowing the use of conditions in transaction/method bodies.
    * `top_comb` is unguarded: statements added to this domain always
      execute. It can be used to reduce combinational path length due to
      multplexers while keeping related combinational and synchronous
      statements together.
    """

    def __init__(self):
        self.main_module = Module()
        self.avoiding_module = Module()
        self.top_module = Module()
        self.d = _AvoidingModuleBuilderDomains(self)
        self.submodules = self.main_module.submodules
        self.domains = self.main_module.domains
        self.fsm: Optional[FSM] = None

    @contextmanager
    def AvoidedIf(self, cond: ValueLike):  # noqa: N802
        with self.main_module.If(cond):
            yield

    @contextmanager
    def If(self, cond: ValueLike):  # noqa: N802
        with self.main_module.If(cond):
            with self.avoiding_module.If(cond):
                yield

    @contextmanager
    def Elif(self, cond):  # noqa: N802
        with self.main_module.Elif(cond):
            with self.avoiding_module.Elif(cond):
                yield

    @contextmanager
    def Else(self):  # noqa: N802
        with self.main_module.Else():
            with self.avoiding_module.Else():
                yield

    @contextmanager
    def Switch(self, test: ValueLike):  # noqa: N802
        with self.main_module.Switch(test):
            with self.avoiding_module.Switch(test):
                yield

    @contextmanager
    def Case(self, *patterns: SwitchKey):  # noqa: N802
        with self.main_module.Case(*patterns):
            with self.avoiding_module.Case(*patterns):
                yield

    @contextmanager
    def Default(self):  # noqa: N802
        with self.main_module.Default():
            with self.avoiding_module.Default():
                yield

    @contextmanager
    def FSM(self, reset: Optional[str] = None, domain: str = "sync", name: str = "fsm"):  # noqa: N802
        old_fsm = self.fsm
        with self.main_module.FSM(reset, domain, name) as fsm:
            self.fsm = fsm
            yield fsm
        self.fsm = old_fsm

    @contextmanager
    def State(self, name: str):  # noqa: N802
        assert self.fsm is not None
        with self.main_module.State(name):
            with self.avoiding_module.If(self.fsm.ongoing(name)):
                yield

    @property
    def next(self) -> NoReturn:
        raise NotImplementedError

    @next.setter
    def next(self, name: str):
        self.main_module.next = name

    @property
    def _MustUse__silence(self):  # noqa: N802
        return self.main_module._MustUse__silence

    @_MustUse__silence.setter
    def _MustUse__silence(self, value):  # noqa: N802
        self.main_module._MustUse__silence = value  # type: ignore
        self.avoiding_module._MustUse__silence = value  # type: ignore
        self.top_module._MustUse__silence = value  # type: ignore

    def elaborate(self, platform):
        self.main_module.submodules._avoiding_module = self.avoiding_module
        self.main_module.submodules._top_module = self.top_module
        return self.main_module


@runtime_checkable
class TransactionBase(Owned, Protocol):
    stack: ClassVar[list[Union["Transaction", "Method"]]] = []
    def_counter: ClassVar[count] = count()
    def_order: int
    defined: bool = False
    name: str
    method_uses: dict["Method", Tuple[ValueLike, ValueLike]]
    relations: list[RelationBase]
    simultaneous_list: list[TransactionOrMethod]
    independent_list: list[TransactionOrMethod]

    def __init__(self):
        self.method_uses: dict["Method", Tuple[ValueLike, ValueLike]] = dict()
        self.relations: list[RelationBase] = []
        self.simultaneous_list: list[TransactionOrMethod] = []
        self.independent_list: list[TransactionOrMethod] = []

    def add_conflict(self, end: TransactionOrMethod, priority: Priority = Priority.UNDEFINED) -> None:
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

    def schedule_before(self, end: TransactionOrMethod) -> None:
        """Adds a priority relation.

        Record that that the given `Transaction` or `Method` needs to be
        scheduled before this `Method` or `Transaction`, without adding
        a conflict. Typical reason is data forwarding.

        Parameters
        ----------
        end: Transaction or Method
            The other `Transaction` or `Method`
        """
        self.relations.append(RelationBase(end=end, priority=Priority.LEFT, conflict=False))

    def use_method(self, method: "Method", arg: ValueLike, enable: ValueLike):
        if method in self.method_uses:
            raise RuntimeError(f"Method '{method.name}' can't be called twice from the same transaction '{self.name}'")
        self.method_uses[method] = (arg, enable)

    def simultaneous(self, *others: TransactionOrMethod) -> None:
        """Adds simultaneity relations.

        The given `Transaction`\\s or `Method``\\s will execute simultaneously
        (in the same clock cycle) with this `Transaction` or `Method`.

        Parameters
        ----------
        *others: Transaction or Method
            The `Transaction`\\s or `Method`\\s to be executed simultaneously.
        """
        self.simultaneous_list += others

    def simultaneous_alternatives(self, *others: TransactionOrMethod) -> None:
        """Adds exclusive simultaneity relations.

        Each of the given `Transaction`\\s or `Method``\\s will execute
        simultaneously (in the same clock cycle) with this `Transaction` or
        `Method`. However, each of the given `Transaction`\\s or `Method`\\s
        will be separately considered for execution.

        Parameters
        ----------
        *others: Transaction or Method
            The `Transaction`\\s or `Method`\\s to be executed simultaneously,
            but mutually exclusive, with this `Transaction` or `Method`.
        """
        self.simultaneous(*others)
        others[0]._independent(*others[1:])

    def _independent(self, *others: TransactionOrMethod) -> None:
        """Adds independence relations.

        This `Transaction` or `Method`, together with all the given
        `Transaction`\\s or `Method`\\s, will never be considered (pairwise)
        for simultaneous execution.

        Warning: this function is an implementation detail, do not use in
        user code.

        Parameters
        ----------
        *others: Transaction or Method
            The `Transaction`\\s or `Method`\\s which, together with this
            `Transaction` or `Method`, need to be independently considered
            for execution.
        """
        self.independent_list += others

    @contextmanager
    def context(self: TransactionOrMethodBound, m: TModule) -> Iterator[TransactionOrMethodBound]:
        parent = TransactionBase.peek()
        if parent is not None:
            parent.schedule_before(self)

        TransactionBase.stack.append(self)

        try:
            yield self
        finally:
            TransactionBase.stack.pop()

    @classmethod
    def get(cls) -> Self:
        ret = cls.peek()
        if ret is None:
            raise RuntimeError("No current body")
        return ret

    @classmethod
    def peek(cls) -> Optional[Self]:
        if not TransactionBase.stack:
            return None
        if not isinstance(TransactionBase.stack[-1], cls):
            raise RuntimeError(f"Current body not a {cls.__name__}")
        return TransactionBase.stack[-1]

    @property
    def owned_name(self):
        if self.owner is not None and self.owner.__class__.__name__ != self.name:
            return f"{self.owner.__class__.__name__}_{self.name}"
        else:
            return self.name


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
        self,
        *,
        name: Optional[str] = None,
        i: MethodLayout = (),
        o: MethodLayout = (),
        nonexclusive: bool = False,
        single_caller: bool = False,
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
        single_caller: bool
            If true, this method is intended to be called from a single
            transaction. An error will be thrown if called from multiple
            transactions.
        """
        super().__init__()
        self.owner, owner_name = get_caller_class_name(default="$method")
        self.name = name or tracer.get_var_name(depth=2, default=owner_name)
        self.ready = Signal(name=self.owned_name + "_ready")
        self.run = Signal(name=self.owned_name + "_run")
        self.data_in = Record(i)
        self.data_out = Record(o)
        self.nonexclusive = nonexclusive
        self.single_caller = single_caller
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

    def proxy(self, m: TModule, method: "Method"):
        """Define as a proxy for another method.

        The calls to this method will be forwarded to `method`.

        Parameters
        ----------
        m : TModule
            Module in which operations on signals should be executed,
            `proxy` uses the combinational domain only.
        method : Method
            Method for which this method is a proxy for.
        """

        @def_method(m, self)
        def _(arg):
            return method(m, arg)

    @contextmanager
    def body(self, m: TModule, *, ready: ValueLike = C(1), out: ValueLike = C(0, 0)) -> Iterator[Record]:
        """Define method body

        The `body` context manager can be used to define the actions
        performed by a `Method` when it's run. Each assignment added to
        a domain under `body` is guarded by the `run` signal.
        Combinational assignments which do not need to be guarded by `run`
        can be added to `m.d.av_comb` or `m.d.top_comb` instead of `m.d.comb`.
        `Method` calls can be performed under `body`.

        Parameters
        ----------
        m : TModule
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
            raise RuntimeError(f"Method '{self.name}' already defined")
        self.def_order = next(TransactionBase.def_counter)

        try:
            m.d.av_comb += self.ready.eq(ready)
            m.d.top_comb += self.data_out.eq(out)
            with self.context(m):
                with m.AvoidedIf(self.run):
                    yield self.data_in
        finally:
            self.defined = True

    def __call__(
        self, m: TModule, arg: Optional[RecordDict] = None, enable: ValueLike = C(1), /, **kwargs: RecordDict
    ) -> Record:
        """Call a method.

        Methods can only be called from transaction and method bodies.
        Calling a `Method` marks, for the purpose of transaction scheduling,
        the dependency between the calling context and the called `Method`.
        It also connects the method's inputs to the parameters and the
        method's outputs to the return value.

        Parameters
        ----------
        m : TModule
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
        arg_rec = Record.like(self.data_in)

        if arg is not None and kwargs:
            raise ValueError(f"Method '{self.name}' call with both keyword arguments and legacy record argument")

        if arg is None:
            arg = kwargs

        enable_sig = Signal(name=self.owned_name + "_enable")
        m.d.av_comb += enable_sig.eq(enable)
        m.d.top_comb += assign(arg_rec, arg, fields=AssignType.ALL)
        TransactionBase.get().use_method(self, arg_rec, enable_sig)

        return self.data_out

    def __repr__(self) -> str:
        return "(method {})".format(self.name)

    def debug_signals(self) -> SignalBundle:
        return [self.ready, self.run, self.data_in, self.data_out]


def def_method(m: TModule, method: Method, ready: ValueLike = C(1)):
    """Define a method.

    This decorator allows to define transactional methods in an
    elegant way using Python's `def` syntax. Internally, `def_method`
    uses `Method.body`.

    The decorated function should take keyword arguments corresponding to the
    fields of the method's input layout. The `**kwargs` syntax is supported.
    Alternatively, it can take one argument named `arg`, which will be a
    record with input signals.

    The returned value can be either a record with the method's output layout
    or a dictionary of outputs.

    Parameters
    ----------
    m: TModule
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
        def _(arg1, arg2):
            return arg1 + arg2

    Alternative syntax (keyword args in dictionary):

    .. highlight:: python
    .. code-block:: python

        @def_method(m, my_sum_method)
        def _(**args):
            return args["arg1"] + args["arg2"]

    Alternative syntax (arg record):

    .. highlight:: python
    .. code-block:: python

        @def_method(m, my_sum_method)
        def _(arg):
            return {"res": arg.arg1 + arg.arg2}
    """

    def decorator(func: Callable[..., Optional[RecordDict]]):
        out = Record.like(method.data_out)
        ret_out = None

        with method.body(m, ready=ready, out=out) as arg:
            ret_out = method_def_helper(method, func, arg, **arg.fields)

        if ret_out is not None:
            m.d.top_comb += assign(out, ret_out, fields=AssignType.ALL)

    return decorator
