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


@dataclass_json
@dataclass
class Profile:
    transactions_and_methods: dict[int, ProfileInfo] = field(default_factory=dict)
    waiting_transactions: dict[int, dict[int, int]] = field(default_factory=dict)
    running: dict[int, dict[int, Optional[int]]] = field(default_factory=dict)

    def encode(self, file_name: str):
        with open(file_name, "w") as fp:
            fp.write(self.to_json())  # type: ignore

    @staticmethod
    def decode(file_name: str):
        with open(file_name, "r") as fp:
            return Profile.from_json(fp.read())  # type: ignore

    def analyze_transactions(self: "Profile") -> list[TransactionStat]:
        stats = {
            i: TransactionStat(info.name, f"{info.src_loc[0]}:{info.src_loc[1]}")
            for i, info in self.transactions_and_methods.items()
            if info.is_transaction
        }

        for k in self.running.keys():
            for i in stats:
                if i in self.waiting_transactions[k]:
                    stats[i].runnable = stats[i].runnable + 1
                elif i in self.running[k]:
                    stats[i].grant = stats[i].grant + 1
                else:
                    stats[i].unused = stats[i].unused + 1

        return list(stats.values())
