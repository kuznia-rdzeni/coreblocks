from collections import defaultdict, deque
from collections.abc import Collection, Sequence, Iterable, Callable, Mapping, Iterator
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
    Self,
    runtime_checkable,
)
from os import environ
from graphlib import TopologicalSorter
from dataclasses import dataclass, replace
from amaranth import *
from amaranth import tracer
from itertools import count, chain, filterfalse, product
from amaranth.hdl.dsl import FSM, _ModuleBuilderDomain

from transactron.utils.assign import AssignArg

from .graph import Owned, OwnershipGraph, Direction
from transactron.utils import *
from transactron.utils.transactron_helpers import _graph_ccs

__all__ = [
    "MethodLayout",
    "Priority",
    "TModule",
    "TransactionManager",
    "TransactionManagerKey",
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
    silence_warning: bool


class Relation(RelationBase):
    start: TransactionOrMethod


class MethodMap:
    def __init__(self, transactions: Iterable["Transaction"]):
        self.methods_by_transaction = dict[Transaction, list[Method]]()
        self.transactions_by_method = defaultdict[Method, list[Transaction]](list)
        self.readiness_by_method_and_transaction = dict[tuple[Transaction, Method], ValueLike]()
        self.method_parents = defaultdict[Method, list[TransactionBase]](list)

        def rec(transaction: Transaction, source: TransactionBase):
            for method, (arg_rec, _) in source.method_uses.items():
                if not method.defined:
                    raise RuntimeError(f"Trying to use method '{method.name}' which is not defined yet")
                if method in self.methods_by_transaction[transaction]:
                    raise RuntimeError(f"Method '{method.name}' can't be called twice from the same transaction")
                self.methods_by_transaction[transaction].append(method)
                self.transactions_by_method[method].append(transaction)
                self.readiness_by_method_and_transaction[(transaction, method)] = method._validate_arguments(arg_rec)
                rec(transaction, method)

        for transaction in transactions:
            self.methods_by_transaction[transaction] = []
            rec(transaction, transaction)

        for transaction_or_method in self.methods_and_transactions:
            for method in transaction_or_method.method_uses.keys():
                self.method_parents[method].append(transaction_or_method)

    def transactions_for(self, elem: TransactionOrMethod) -> Collection["Transaction"]:
        if isinstance(elem, Transaction):
            return [elem]
        else:
            return self.transactions_by_method[elem]

    @property
    def methods(self) -> Collection["Method"]:
        return self.transactions_by_method.keys()

    @property
    def transactions(self) -> Collection["Transaction"]:
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
        conflicts = [ccl[j].grant for j in range(k) if ccl[j] in gr[transaction]]
        noconflict = ~Cat(conflicts).any()
        m.d.comb += transaction.grant.eq(transaction.request & transaction.runnable & noconflict)
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
        m.d.comb += sched.requests[k].eq(transaction.request & transaction.runnable)
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

        def transactions_exclusive(trans1: Transaction, trans2: Transaction):
            tms1 = [trans1] + method_map.methods_by_transaction[trans1]
            tms2 = [trans2] + method_map.methods_by_transaction[trans2]

            # if first transaction is exclusive with the second transaction, or this is true for
            # any called methods, the transactions will never run at the same time
            for tm1, tm2 in product(tms1, tms2):
                if tm1.ctrl_path.exclusive_with(tm2.ctrl_path):
                    return True

            return False

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
                    if transaction1 is not transaction2 and not transactions_exclusive(transaction1, transaction2):
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
                if end.def_order < start.def_order and not relation["silence_warning"]:
                    raise RuntimeError(f"{start.name!r} scheduled before {end.name!r}, but defined afterwards")

            for trans_start in method_map.transactions_for(start):
                for trans_end in method_map.transactions_for(end):
                    conflict = relation["conflict"] and not transactions_exclusive(trans_start, trans_end)
                    add_edge(trans_start, trans_end, relation["priority"], conflict)

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
            method.src_loc = transaction.src_loc
            method.ready = transaction.request
            method.run = transaction.grant
            method.defined = transaction.defined
            method.method_calls = transaction.method_calls
            method.method_uses = transaction.method_uses
            method.relations = transaction.relations
            method.def_order = transaction.def_order
            method.ctrl_path = transaction.ctrl_path
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

        for elem in method_map.methods_and_transactions:
            elem._set_method_uses(m)

        for transaction in self.transactions:
            ready = [
                method_map.readiness_by_method_and_transaction[transaction, method]
                for method in method_map.methods_by_transaction[transaction]
            ]
            m.d.comb += transaction.runnable.eq(Cat(ready).all())

        ccs = _graph_ccs(rgr)
        m.submodules._transactron_schedulers = ModuleConnector(
            *[self.cc_scheduler(method_map, cgr, cc, porder) for cc in ccs]
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

        if "TRANSACTRON_VERBOSE" in environ:
            self.print_info(cgr, porder, ccs, method_map)

        return m

    def print_info(
        self, cgr: TransactionGraph, porder: PriorityOrder, ccs: list[GraphCC["Transaction"]], method_map: MethodMap
    ):
        print("Transactron statistics")
        print(f"\tMethods: {len(method_map.methods)}")
        print(f"\tTransactions: {len(method_map.transactions)}")
        print(f"\tIndependent subgraphs: {len(ccs)}")
        print(f"\tAvg callers per method: {average_dict_of_lists(method_map.transactions_by_method):.2f}")
        print(f"\tAvg conflicts per transaction: {average_dict_of_lists(cgr):.2f}")
        print("")
        print("Transaction subgraphs")
        for cc in ccs:
            ccl = list(cc)
            ccl.sort(key=lambda t: porder[t])
            for t in ccl:
                print(f"\t{t.name}")
            print("")
        print("Calling transactions per method")
        for m, ts in method_map.transactions_by_method.items():
            print(f"\t{m.owned_name}: {m.src_loc[0]}:{m.src_loc[1]}")
            for t in ts:
                print(f"\t\t{t.name}: {t.src_loc[0]}:{t.src_loc[1]}")
            print("")
        print("Called methods per transaction")
        for t, ms in method_map.methods_by_transaction.items():
            print(f"\t{t.name}: {t.src_loc[0]}:{t.src_loc[1]}")
            for m in ms:
                print(f"\t\t{m.owned_name}: {m.src_loc[0]}:{m.src_loc[1]}")
            print("")

    def visual_graph(self, fragment):
        graph = OwnershipGraph(fragment)
        method_map = MethodMap(self.transactions)
        for method, transactions in method_map.transactions_by_method.items():
            if len(method.data_in.as_value()) > len(method.data_out.as_value()):
                direction = Direction.IN
            elif method.data_in.shape().size < method.data_out.shape().size:
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


@dataclass(frozen=True)
class TransactionManagerKey(SimpleKey[TransactionManager]):
    pass


class TransactionModule(Elaboratable):
    """
    `TransactionModule` is used as wrapper on `Elaboratable` classes,
    which adds support for transactions. It creates a
    `TransactionManager` which will handle transaction scheduling
    and can be used in definition of `Method`\\s and `Transaction`\\s.
    The `TransactionManager` is stored in a `DependencyManager`.
    """

    def __init__(
        self,
        elaboratable: HasElaborate,
        dependency_manager: Optional[DependencyManager] = None,
        transaction_manager: Optional[TransactionManager] = None,
    ):
        """
        Parameters
        ----------
        elaboratable: HasElaborate
            The `Elaboratable` which should be wrapped to add support for
            transactions and methods.
        dependency_manager: DependencyManager, optional
            The `DependencyManager` to use inside the transaction module.
            If omitted, a new one is created.
        transaction_manager: TransactionManager, optional
            The `TransactionManager` to use inside the transaction module.
            If omitted, a new one is created.
        """
        if transaction_manager is None:
            transaction_manager = TransactionManager()
        if dependency_manager is None:
            dependency_manager = DependencyManager()
        self.manager = dependency_manager
        self.manager.add_dependency(TransactionManagerKey(), transaction_manager)
        self.elaboratable = elaboratable

    def context(self) -> DependencyContext:
        return DependencyContext(self.manager)

    def elaborate(self, platform):
        with silence_mustuse(self.manager.get_dependency(TransactionManagerKey())):
            with self.context():
                elaboratable = Fragment.get(self.elaboratable, platform)

        m = Module()

        m.submodules.main_module = elaboratable
        m.submodules.transactionManager = self.manager.get_dependency(TransactionManagerKey())

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


class EnterType(Enum):
    """Characterizes stack behavior of Amaranth's context managers for control structures."""

    #: Used for `m.If`, `m.Switch` and `m.FSM`.
    PUSH = auto()
    #: Used for `m.Elif` and `m.Else`.
    ADD = auto()
    #: Used for `m.Case`, `m.Default` and `m.State`.
    ENTRY = auto()


@dataclass(frozen=True)
class PathEdge:
    """Describes an edge in Amaranth's control tree.

    Attributes
    ----------
    alt : int
        Which alternative (e.g. case of `m.If` or m.Switch`) is described.
    par : int
        Which parallel control structure (e.g. `m.If` at the same level) is described.
    """

    alt: int = 0
    par: int = 0


@dataclass
class CtrlPath:
    """Describes a path in Amaranth's control tree.

    Attributes
    ----------
    module : int
        Unique number of the module the path refers to.
    path : list[PathEdge]
        Path in the control tree, starting from the root.
    """

    module: int
    path: list[PathEdge]

    def exclusive_with(self, other: "CtrlPath"):
        """Decides if this path is mutually exclusive with some other path.

        Paths are mutually exclusive if they refer to the same module and
        diverge on different alternatives of the same control structure.

        Arguments
        ---------
        other : CtrlPath
            The other path this path is compared to.
        """
        common_prefix = []
        for a, b in zip(self.path, other.path):
            if a == b:
                common_prefix.append(a)
            elif a.par != b.par:
                return False
            else:
                break

        return (
            self.module == other.module
            and len(common_prefix) != len(self.path)
            and len(common_prefix) != len(other.path)
        )


class CtrlPathBuilder:
    """Constructs control paths.

    Used internally by `TModule`."""

    def __init__(self, module: int):
        """
        Parameters
        ----------
        module: int
            Unique module identifier.
        """
        self.module = module
        self.ctrl_path: list[PathEdge] = []
        self.previous: Optional[PathEdge] = None

    @contextmanager
    def enter(self, enter_type=EnterType.PUSH):
        et = EnterType

        match enter_type:
            case et.ADD:
                assert self.previous is not None
                self.ctrl_path.append(replace(self.previous, alt=self.previous.alt + 1))
            case et.ENTRY:
                self.ctrl_path[-1] = replace(self.ctrl_path[-1], alt=self.ctrl_path[-1].alt + 1)
            case et.PUSH:
                if self.previous is not None:
                    self.ctrl_path.append(PathEdge(par=self.previous.par + 1))
                else:
                    self.ctrl_path.append(PathEdge())
        self.previous = None
        try:
            yield
        finally:
            if enter_type in [et.PUSH, et.ADD]:
                self.previous = self.ctrl_path.pop()

    def build_ctrl_path(self):
        """Returns the current control path."""
        return CtrlPath(self.module, self.ctrl_path[:])


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

    __next_uid = 0

    def __init__(self):
        self.main_module = Module()
        self.avoiding_module = Module()
        self.top_module = Module()
        self.d = _AvoidingModuleBuilderDomains(self)
        self.submodules = self.main_module.submodules
        self.domains = self.main_module.domains
        self.fsm: Optional[FSM] = None
        self.uid = TModule.__next_uid
        self.path_builder = CtrlPathBuilder(self.uid)
        TModule.__next_uid += 1

    @contextmanager
    def AvoidedIf(self, cond: ValueLike):  # noqa: N802
        with self.main_module.If(cond):
            with self.path_builder.enter(EnterType.PUSH):
                yield

    @contextmanager
    def If(self, cond: ValueLike):  # noqa: N802
        with self.main_module.If(cond):
            with self.avoiding_module.If(cond):
                with self.path_builder.enter(EnterType.PUSH):
                    yield

    @contextmanager
    def Elif(self, cond):  # noqa: N802
        with self.main_module.Elif(cond):
            with self.avoiding_module.Elif(cond):
                with self.path_builder.enter(EnterType.ADD):
                    yield

    @contextmanager
    def Else(self):  # noqa: N802
        with self.main_module.Else():
            with self.avoiding_module.Else():
                with self.path_builder.enter(EnterType.ADD):
                    yield

    @contextmanager
    def Switch(self, test: ValueLike):  # noqa: N802
        with self.main_module.Switch(test):
            with self.avoiding_module.Switch(test):
                with self.path_builder.enter(EnterType.PUSH):
                    yield

    @contextmanager
    def Case(self, *patterns: SwitchKey):  # noqa: N802
        with self.main_module.Case(*patterns):
            with self.avoiding_module.Case(*patterns):
                with self.path_builder.enter(EnterType.ENTRY):
                    yield

    @contextmanager
    def Default(self):  # noqa: N802
        with self.main_module.Default():
            with self.avoiding_module.Default():
                with self.path_builder.enter(EnterType.ENTRY):
                    yield

    @contextmanager
    def FSM(self, reset: Optional[str] = None, domain: str = "sync", name: str = "fsm"):  # noqa: N802
        old_fsm = self.fsm
        with self.main_module.FSM(reset, domain, name) as fsm:
            self.fsm = fsm
            with self.path_builder.enter(EnterType.PUSH):
                yield fsm
        self.fsm = old_fsm

    @contextmanager
    def State(self, name: str):  # noqa: N802
        assert self.fsm is not None
        with self.main_module.State(name):
            with self.avoiding_module.If(self.fsm.ongoing(name)):
                with self.path_builder.enter(EnterType.ENTRY):
                    yield

    @property
    def next(self) -> NoReturn:
        raise NotImplementedError

    @next.setter
    def next(self, name: str):
        self.main_module.next = name

    @property
    def ctrl_path(self):
        return self.path_builder.build_ctrl_path()

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
    src_loc: SrcLoc
    method_uses: dict["Method", tuple[MethodStruct, Signal]]
    method_calls: defaultdict["Method", list[tuple[CtrlPath, MethodStruct, ValueLike]]]
    relations: list[RelationBase]
    simultaneous_list: list[TransactionOrMethod]
    independent_list: list[TransactionOrMethod]
    ctrl_path: CtrlPath = CtrlPath(-1, [])

    def __init__(self, *, src_loc: int | SrcLoc):
        self.src_loc = get_src_loc(src_loc)
        self.method_uses = {}
        self.method_calls = defaultdict(list)
        self.relations = []
        self.simultaneous_list = []
        self.independent_list = []

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
        self.relations.append(
            RelationBase(end=end, priority=priority, conflict=True, silence_warning=self.owner != end.owner)
        )

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
        self.relations.append(
            RelationBase(end=end, priority=Priority.LEFT, conflict=False, silence_warning=self.owner != end.owner)
        )

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
        self.ctrl_path = m.ctrl_path

        parent = TransactionBase.peek()
        if parent is not None:
            parent.schedule_before(self)

        TransactionBase.stack.append(self)

        try:
            yield self
        finally:
            TransactionBase.stack.pop()
            self.defined = True

    def _set_method_uses(self, m: ModuleLike):
        for method, calls in self.method_calls.items():
            arg_rec, enable_sig = self.method_uses[method]
            if len(calls) == 1:
                m.d.comb += arg_rec.eq(calls[0][1])
                m.d.comb += enable_sig.eq(calls[0][2])
            else:
                call_ens = Cat([en for _, _, en in calls])

                for i in OneHotSwitchDynamic(m, call_ens):
                    m.d.comb += arg_rec.eq(calls[i][1])
                    m.d.comb += enable_sig.eq(1)

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
    runnable: Signal, out
        Signals that all used methods are ready.
    grant: Signal, out
        Signals that the transaction is granted by the `TransactionManager`,
        and all used methods are called.
    """

    def __init__(
        self, *, name: Optional[str] = None, manager: Optional[TransactionManager] = None, src_loc: int | SrcLoc = 0
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

    def __repr__(self) -> str:
        return "(transaction {})".format(self.name)

    def debug_signals(self) -> SignalBundle:
        return [self.request, self.runnable, self.grant]


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
    using Amaranth structures (`View` with a `StructLayout`). The transfer
    can take place in both directions at the same time: from the called
    `Method` to the caller (`data_out`) and from the caller to the called
    `Method` (`data_in`).

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
    data_in: MethodStruct, out
        Contains the data passed to the `Method` by the caller
        (a `Transaction` or another `Method`).
    data_out: MethodStruct, in
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
        src_loc: int | SrcLoc = 0,
    ):
        """
        Parameters
        ----------
        name: str or None
            Name hint for this `Method`. If `None` (default) the name is
            inferred from the variable name this `Method` is assigned to.
        i: method layout
            The format of `data_in`.
        o: method layout
            The format of `data_out`.
        nonexclusive: bool
            If true, the method is non-exclusive: it can be called by multiple
            transactions in the same clock cycle. If such a situation happens,
            the method still is executed only once, and each of the callers
            receive its output. Nonexclusive methods cannot have inputs.
        single_caller: bool
            If true, this method is intended to be called from a single
            transaction. An error will be thrown if called from multiple
            transactions.
        src_loc: int | SrcLoc
            How many stack frames deep the source location is taken from.
            Alternatively, the source location to use instead of the default.
        """
        super().__init__(src_loc=get_src_loc(src_loc))
        self.owner, owner_name = get_caller_class_name(default="$method")
        self.name = name or tracer.get_var_name(depth=2, default=owner_name)
        self.ready = Signal(name=self.owned_name + "_ready")
        self.run = Signal(name=self.owned_name + "_run")
        self.data_in: MethodStruct = Signal(from_method_layout(i))
        self.data_out: MethodStruct = Signal(from_method_layout(o))
        self.nonexclusive = nonexclusive
        self.single_caller = single_caller
        self.validate_arguments: Optional[Callable[..., ValueLike]] = None
        if nonexclusive:
            assert len(self.data_in.as_value()) == 0

    @property
    def layout_in(self):
        return self.data_in.shape()

    @property
    def layout_out(self):
        return self.data_out.shape()

    @staticmethod
    def like(other: "Method", *, name: Optional[str] = None, src_loc: int | SrcLoc = 0) -> "Method":
        """Constructs a new `Method` based on another.

        The returned `Method` has the same input/output data layouts as the
        `other` `Method`.

        Parameters
        ----------
        other : Method
            The `Method` which serves as a blueprint for the new `Method`.
        name : str, optional
            Name of the new `Method`.
        src_loc: int | SrcLoc
            How many stack frames deep the source location is taken from.
            Alternatively, the source location to use instead of the default.

        Returns
        -------
        Method
            The freshly constructed `Method`.
        """
        return Method(name=name, i=other.layout_in, o=other.layout_out, src_loc=get_src_loc(src_loc))

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
    def body(
        self,
        m: TModule,
        *,
        ready: ValueLike = C(1),
        out: ValueLike = C(0, 0),
        validate_arguments: Optional[Callable[..., ValueLike]] = None,
    ) -> Iterator[MethodStruct]:
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
        out : Value, in
            Data generated by the `Method`, which will be passed to
            the caller (a `Transaction` or another `Method`). Assigned
            combinationally to the `data_out` attribute.
        validate_arguments: Optional[Callable[..., ValueLike]]
            Function that takes input arguments used to call the method
            and checks whether the method can be called with those arguments.
            It instantiates a combinational circuit for each
            method caller. By default, there is no function, so all arguments
            are accepted.

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
        self.validate_arguments = validate_arguments

        m.d.av_comb += self.ready.eq(ready)
        m.d.top_comb += self.data_out.eq(out)
        with self.context(m):
            with m.AvoidedIf(self.run):
                yield self.data_in

    def _validate_arguments(self, arg_rec: MethodStruct) -> ValueLike:
        if self.validate_arguments is not None:
            return self.ready & method_def_helper(self, self.validate_arguments, arg_rec)
        return self.ready

    def __call__(
        self, m: TModule, arg: Optional[AssignArg] = None, enable: ValueLike = C(1), /, **kwargs: AssignArg
    ) -> MethodStruct:
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
            Call argument. Can be passed as a `View` of the method's
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
        data_out : MethodStruct
            The result of the method call.

        Examples
        --------
        .. highlight:: python
        .. code-block:: python

            m = Module()
            with Transaction().body(m):
                ret = my_sum_method(m, arg1=2, arg2=3)

        Alternative syntax:

        .. highlight:: python
        .. code-block:: python

            with Transaction().body(m):
                ret = my_sum_method(m, {"arg1": 2, "arg2": 3})
        """
        arg_rec = Signal.like(self.data_in)

        if arg is not None and kwargs:
            raise ValueError(f"Method '{self.name}' call with both keyword arguments and legacy record argument")

        if arg is None:
            arg = kwargs

        enable_sig = Signal(name=self.owned_name + "_enable")
        m.d.av_comb += enable_sig.eq(enable)
        m.d.top_comb += assign(arg_rec, arg, fields=AssignType.ALL)

        caller = TransactionBase.get()
        if not all(ctrl_path.exclusive_with(m.ctrl_path) for ctrl_path, _, _ in caller.method_calls[self]):
            raise RuntimeError(f"Method '{self.name}' can't be called twice from the same caller '{caller.name}'")
        caller.method_calls[self].append((m.ctrl_path, arg_rec, enable_sig))

        if self not in caller.method_uses:
            arg_rec_use = Signal(self.layout_in)
            arg_rec_enable_sig = Signal()
            caller.method_uses[self] = (arg_rec_use, arg_rec_enable_sig)

        return self.data_out

    def __repr__(self) -> str:
        return "(method {})".format(self.name)

    def debug_signals(self) -> SignalBundle:
        return [self.ready, self.run, self.data_in, self.data_out]


def def_method(
    m: TModule,
    method: Method,
    ready: ValueLike = C(1),
    validate_arguments: Optional[Callable[..., ValueLike]] = None,
):
    """Define a method.

    This decorator allows to define transactional methods in an
    elegant way using Python's `def` syntax. Internally, `def_method`
    uses `Method.body`.

    The decorated function should take keyword arguments corresponding to the
    fields of the method's input layout. The `**kwargs` syntax is supported.
    Alternatively, it can take one argument named `arg`, which will be a
    structure with input signals.

    The returned value can be either a structure with the method's output layout
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
    validate_arguments: Optional[Callable[..., ValueLike]]
        Function that takes input arguments used to call the method
        and checks whether the method can be called with those arguments.
        It instantiates a combinational circuit for each
        method caller. By default, there is no function, so all arguments
        are accepted.

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

    Alternative syntax (arg structure):

    .. highlight:: python
    .. code-block:: python

        @def_method(m, my_sum_method)
        def _(arg):
            return {"res": arg.arg1 + arg.arg2}
    """

    def decorator(func: Callable[..., Optional[AssignArg]]):
        out = Signal(method.layout_out)
        ret_out = None

        with method.body(m, ready=ready, out=out, validate_arguments=validate_arguments) as arg:
            ret_out = method_def_helper(method, func, arg)

        if ret_out is not None:
            m.d.top_comb += assign(out, ret_out, fields=AssignType.ALL)

    return decorator
