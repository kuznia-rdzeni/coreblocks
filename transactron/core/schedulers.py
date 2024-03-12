from amaranth import *
from typing import TYPE_CHECKING
from transactron.utils import *

if TYPE_CHECKING:
    from .manager import MethodMap, TransactionGraph, TransactionGraphCC, PriorityOrder

__all__ = ["eager_deterministic_cc_scheduler", "trivial_roundrobin_cc_scheduler"]


def eager_deterministic_cc_scheduler(
    method_map: "MethodMap", gr: "TransactionGraph", cc: "TransactionGraphCC", porder: "PriorityOrder"
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
    method_map: "MethodMap", gr: "TransactionGraph", cc: "TransactionGraphCC", porder: "PriorityOrder"
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
