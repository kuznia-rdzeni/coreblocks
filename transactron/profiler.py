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
class RunStat:
    name: str
    src_loc: str
    locked: int = 0
    run: int = 0

    @staticmethod
    def make(info: ProfileInfo):
        return RunStat(info.name, f"{info.src_loc[0]}:{info.src_loc[1]}")


@dataclass
class RunStatNode:
    stat: RunStat
    callers: dict[int, "RunStatNode"] = field(default_factory=dict)

    @staticmethod
    def make(info: ProfileInfo):
        return RunStatNode(RunStat.make(info))


@dataclass_json
@dataclass
class CycleProfile:
    locked: dict[int, int] = field(default_factory=dict)
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

    def analyze_methods(self, recursive=True) -> list[RunStat]:
        stats = {i: RunStatNode.make(info) for i, info in self.transactions_and_methods.items()}

        def rec(c: CycleProfile, node: RunStatNode, i: int):
            node.stat.run += 1
            caller = c.running[i]
            if recursive and caller is not None:
                if caller not in stats[i].callers:
                    node.callers[caller] = RunStatNode.make(self.transactions_and_methods[caller])
                rec(c, node.callers[caller], caller)

        for c in self.cycles:
            for i in c.running:
                rec(c, stats[i], i)

            for i in c.locked:
                stats[i].stat.locked += 1

        return list(map(lambda node: node.stat, stats.values()))
