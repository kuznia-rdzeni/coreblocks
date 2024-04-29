import os
from collections import defaultdict
from typing import Optional
from dataclasses import dataclass, field
from dataclasses_json import dataclass_json
from transactron.utils import SrcLoc, IdGenerator
from transactron.core import TransactionManager
from transactron.core.manager import MethodMap


__all__ = [
    "ProfileInfo",
    "ProfileData",
    "RunStat",
    "RunStatNode",
    "Profile",
    "TransactionSamples",
    "MethodSamples",
    "ProfileSamples",
]


@dataclass_json
@dataclass
class ProfileInfo:
    """Information about transactions and methods.

    In `Profile`, transactions and methods are referred to by their unique ID
    numbers.

    Attributes
    ----------
    name : str
        The name.
    src_loc : SrcLoc
        Source location.
    is_transaction : bool
        If true, this object describes a transaction; if false, a method.
    """

    name: str
    src_loc: SrcLoc
    is_transaction: bool


@dataclass
class ProfileData:
    """Information about transactions and methods from the transaction manager.

    This data is required for transaction profile generation in simulators.
    Transactions and methods are referred to by their unique ID numbers.

    Attributes
    ----------
    transactions_and_methods: dict[int, ProfileInfo]
        Information about individual transactions and methods.
    method_parents: dict[int, list[int]]
        Lists the callers (transactions and methods) for each method. Key is
        method ID.
    transactions_by_method: dict[int, list[int]]
        Lists which transactions are calling each method. Key is method ID.
    transaction_conflicts: dict[int, list[int]]
        List which other transactions conflict with each transaction.
    """

    transactions_and_methods: dict[int, ProfileInfo]
    method_parents: dict[int, list[int]]
    transactions_by_method: dict[int, list[int]]
    transaction_conflicts: dict[int, list[int]]

    @staticmethod
    def make(transaction_manager: TransactionManager):
        transactions_and_methods = dict[int, ProfileInfo]()
        method_parents = dict[int, list[int]]()
        transactions_by_method = dict[int, list[int]]()
        transaction_conflicts = dict[int, list[int]]()

        method_map = MethodMap(transaction_manager.transactions)
        cgr, _ = TransactionManager._conflict_graph(method_map)
        get_id = IdGenerator()

        def local_src_loc(src_loc: SrcLoc):
            return (os.path.relpath(src_loc[0]), src_loc[1])

        for transaction in method_map.transactions:
            transactions_and_methods[get_id(transaction)] = ProfileInfo(
                transaction.owned_name, local_src_loc(transaction.src_loc), True
            )

        for method in method_map.methods:
            transactions_and_methods[get_id(method)] = ProfileInfo(
                method.owned_name, local_src_loc(method.src_loc), False
            )
            method_parents[get_id(method)] = [get_id(t_or_m) for t_or_m in method_map.method_parents[method]]
            transactions_by_method[get_id(method)] = [
                get_id(t_or_m) for t_or_m in method_map.transactions_by_method[method]
            ]

        for transaction, transactions in cgr.items():
            transaction_conflicts[get_id(transaction)] = [get_id(transaction2) for transaction2 in transactions]

        return (
            ProfileData(transactions_and_methods, method_parents, transactions_by_method, transaction_conflicts),
            get_id,
        )


@dataclass
class RunStat:
    """Collected statistics about a transaction or method.

    Attributes
    ----------
    name : str
        The name.
    src_loc : SrcLoc
        Source location.
    locked : int
        For methods: the number of cycles this method was locked because of
        a disabled call (a call under a false condition). For transactions:
        the number of cycles this transaction was ready to run, but did not
        run because a conflicting transaction has run instead.
    """

    name: str
    src_loc: str
    locked: int = 0
    run: int = 0

    @staticmethod
    def make(info: ProfileInfo):
        return RunStat(info.name, f"{info.src_loc[0]}:{info.src_loc[1]}")


@dataclass
class RunStatNode:
    """A statistics tree. Summarizes call graph information.

    Attributes
    ----------
    stat : RunStat
        Statistics.
    callers : dict[int, RunStatNode]
        Statistics for the method callers. For transactions, this is empty.
    """

    stat: RunStat
    callers: dict[int, "RunStatNode"] = field(default_factory=dict)

    @staticmethod
    def make(info: ProfileInfo):
        return RunStatNode(RunStat.make(info))


@dataclass
class TransactionSamples:
    """Runtime value of transaction control signals in a given clock cycle.

    Attributes
    ----------
    request: bool
        The value of the transaction's ``request`` signal.
    runnable: bool
        The value of the transaction's ``runnable`` signal.
    grant: bool
        The value of the transaction's ``grant`` signal.
    """

    request: bool
    runnable: bool
    grant: bool


@dataclass
class MethodSamples:
    """Runtime value of method control signals in a given clock cycle.

    Attributes
    ----------
    run: bool
        The value of the method's ``run`` signal.
    """

    run: bool


@dataclass
class ProfileSamples:
    """Runtime values of all transaction and method control signals.

    Attributes
    ----------
    transactions: dict[int, TransactionSamples]
        Runtime values of transaction control signals for each transaction.
    methods: dict[int, MethodSamples]
        Runtime values of method control signals for each method.
    """

    transactions: dict[int, TransactionSamples] = field(default_factory=dict)
    methods: dict[int, MethodSamples] = field(default_factory=dict)


@dataclass_json
@dataclass
class CycleProfile:
    """Profile information for a single clock cycle.

    Transactions and methods are referred to by unique IDs.

    Attributes
    ----------
    locked : dict[int, int]
        For each transaction which didn't run because of a conflict, the
        transaction which has run instead. For each method which was used
        but didn't run because of a disabled call, the caller which
        used it.
    running : dict[int, Optional[int]]
        For each running method, its caller. Running transactions don't
        have a caller (the value is `None`).
    """

    locked: dict[int, int] = field(default_factory=dict)
    running: dict[int, Optional[int]] = field(default_factory=dict)

    @staticmethod
    def make(samples: ProfileSamples, data: ProfileData):
        cprof = CycleProfile()

        for transaction_id, transaction_samples in samples.transactions.items():
            if transaction_samples.grant:
                cprof.running[transaction_id] = None
            elif transaction_samples.request and transaction_samples.runnable:
                for transaction2_id in data.transaction_conflicts[transaction_id]:
                    if samples.transactions[transaction2_id].grant:
                        cprof.locked[transaction_id] = transaction2_id

        running = set(cprof.running)
        for method_id, method_samples in samples.methods.items():
            if method_samples.run:
                running.add(method_id)

        locked_methods = set[int]()
        for method_id in samples.methods.keys():
            if method_id not in running:
                if any(transaction_id in running for transaction_id in data.transactions_by_method[method_id]):
                    locked_methods.add(method_id)

        for method_id in samples.methods.keys():
            if method_id in running:
                for t_or_m_id in data.method_parents[method_id]:
                    if t_or_m_id in running:
                        cprof.running[method_id] = t_or_m_id
            elif method_id in locked_methods:
                caller = next(
                    t_or_m_id
                    for t_or_m_id in data.method_parents[method_id]
                    if t_or_m_id in running or t_or_m_id in locked_methods
                )
                cprof.locked[method_id] = caller

        return cprof


@dataclass_json
@dataclass
class Profile:
    """Transactron execution profile.

    Can be saved by the simulator, and then restored by an analysis tool.
    In the profile data structure, methods and transactions are referred to
    by their unique ID numbers.

    Attributes
    ----------
    transactions_and_methods : dict[int, ProfileInfo]
        Information about transactions and methods indexed by ID numbers.
    cycles : list[CycleProfile]
        Profile information for each cycle of the simulation.
    """

    transactions_and_methods: dict[int, ProfileInfo] = field(default_factory=dict)
    cycles: list[CycleProfile] = field(default_factory=list)

    def encode(self, file_name: str):
        with open(file_name, "w") as fp:
            fp.write(self.to_json())  # type: ignore

    @staticmethod
    def decode(file_name: str) -> "Profile":
        with open(file_name, "r") as fp:
            return Profile.from_json(fp.read())  # type: ignore

    def analyze_transactions(self, recursive=False) -> list[RunStatNode]:
        stats = {i: RunStatNode.make(info) for i, info in self.transactions_and_methods.items() if info.is_transaction}

        def rec(c: CycleProfile, node: RunStatNode, i: int):
            if i in c.running:
                node.stat.run += 1
            elif i in c.locked:
                node.stat.locked += 1
            if recursive:
                for j in called[i]:
                    if j not in node.callers:
                        node.callers[j] = RunStatNode.make(self.transactions_and_methods[j])
                    rec(c, node.callers[j], j)

        for c in self.cycles:
            called = defaultdict[int, set[int]](set)

            for i, j in c.running.items():
                if j is not None:
                    called[j].add(i)

            for i, j in c.locked.items():
                called[j].add(i)

            for i in c.running:
                if i in stats:
                    rec(c, stats[i], i)

            for i in c.locked:
                if i in stats:
                    stats[i].stat.locked += 1

        return list(stats.values())

    def analyze_methods(self, recursive=False) -> list[RunStatNode]:
        stats = {
            i: RunStatNode.make(info) for i, info in self.transactions_and_methods.items() if not info.is_transaction
        }

        def rec(c: CycleProfile, node: RunStatNode, i: int, locking_call=False):
            if i in c.running:
                if not locking_call:
                    node.stat.run += 1
                else:
                    node.stat.locked += 1
                caller = c.running[i]
            else:
                node.stat.locked += 1
                caller = c.locked[i]
            if recursive and caller is not None:
                if caller not in node.callers:
                    node.callers[caller] = RunStatNode.make(self.transactions_and_methods[caller])
                rec(c, node.callers[caller], caller, locking_call)

        for c in self.cycles:
            for i in c.running:
                if i in stats:
                    rec(c, stats[i], i)

            for i in c.locked:
                if i in stats:
                    rec(c, stats[i], i, locking_call=True)

        return list(stats.values())
