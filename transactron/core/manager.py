from amaranth import *
from typing import Tuple, Mapping, Sequence
from collections import defaultdict, deque
from itertools import chain, product, filterfalse
from graphlib import TopologicalSorter
from .relation_database import MethodMap, Priority, Relation
from .transaction import Transaction
from .method import Method
from .modules import TModule
from .schedulers import eager_deterministic_cc_scheduler
from .typing import TransactionGraph, PriorityOrder, TransactionScheduler, ValueLike, TransactionOrMethod, SignalBundle
from ..graph import OwnershipGraph, Direction
from .._utils import _graph_ccs
from coreblocks.utils import silence_mustuse
from coreblocks.utils import ModuleConnector
from coreblocks.utils.utils import OneHotSwitchDynamic

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
