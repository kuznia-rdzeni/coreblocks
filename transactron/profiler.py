from typing import Optional
from dataclasses import dataclass, field
from transactron.utils import SrcLoc
from dataclasses_json import dataclass_json


__all__ = ["ProfileInfo", "Profile", "TransactionStat"]


@dataclass_json
@dataclass
class ProfileInfo:
    name: str
    src_loc: SrcLoc
    is_transaction: bool


@dataclass
class TransactionStat:
    name: str
    src_loc: str
    unused: int = 0
    runnable: int = 0
    grant: int = 0


@dataclass
class RunStat:
    name: str
    src_loc: str
    run: int = 0


@dataclass
class RunStatNode:
    stat: RunStat
    callers: dict[int, "RunStatNode"] = {}


@dataclass_json
@dataclass
class CycleProfile:
    waiting_transactions: dict[int, int] = field(default_factory=dict)
    locked_methods: dict[int, int] = field(default_factory=dict)
    running: dict[int, Optional[int]] = field(default_factory=dict)


@dataclass_json
@dataclass
class Profile:
    transactions_and_methods: dict[int, ProfileInfo] = field(default_factory=dict)
    cycles: list[CycleProfile] = field(default_factory=list)

    def encode(self, file_name: str):
        with open(file_name, "w") as fp:
            fp.write(self.to_json())  # type: ignore

    @staticmethod
    def decode(file_name: str):
        with open(file_name, "r") as fp:
            return Profile.from_json(fp.read())  # type: ignore

    def analyze_transactions(self) -> list[TransactionStat]:
        stats = {
            i: TransactionStat(info.name, f"{info.src_loc[0]}:{info.src_loc[1]}")
            for i, info in self.transactions_and_methods.items()
            if info.is_transaction
        }

        for c in self.cycles:
            for i in stats:
                if i in c.waiting_transactions:
                    stats[i].runnable += 1
                elif i in c.running:
                    stats[i].grant += 1
                else:
                    stats[i].unused += 1

        return list(stats.values())

    def analyze_methods(self, recursive=True) -> list[RunStat]:
        stats: dict[int, RunStatNode] = {
            i: RunStatNode(RunStat(info.name, f"{info.src_loc[0]}:{info.src_loc[1]}"))
            for i, info in self.transactions_and_methods.items()
        }

        def rec(c: CycleProfile, caller: int):
            stats[caller].stat.run += 1
            caller1 = c.running[caller]
            if caller1 is not None:
                rec(c, caller1)

        for c in self.cycles:
            for i, caller in c.running.items():
                stats[i].stat.run += 1
                if recursive and caller is not None:
                    rec(c, caller)

        return list(map(lambda node: node.stat, stats.values()))
