from amaranth import *
from typing import TypeAlias
from .._utils import Graph, GraphCC, Scheduler
from .method import Method
from .transaction import Transaction
from .relation_database import MethodMap
from .typing import TransactionGraph, TransactionGraphCC, PriorityOrder

__all__ = [
    "eager_deterministic_cc_scheduler",
    "trivial_roundrobin_cc_scheduler",
        ]


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
