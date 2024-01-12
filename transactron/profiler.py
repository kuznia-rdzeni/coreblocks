from collections import defaultdict
from typing import Optional
from dataclasses import dataclass, field
from transactron.utils import SrcLoc
from dataclasses_json import dataclass_json


__all__ = ["ProfileInfo", "Profile"]


@dataclass_json
@dataclass
class ProfileInfo:
    """Information about transactions and methods. In `Profile`, transactions
    and methods are referred to by their unique ID numbers.

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
