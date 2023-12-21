import json
from typing import Optional
from dataclasses import dataclass, is_dataclass, asdict, field
from transactron.utils import SrcLoc


__ALL__ = ["ProfileInfo", "Profile"]


class ProfileJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if is_dataclass(o):
            return asdict(o)
        return super().default(o)


@dataclass
class ProfileInfo:
    name: str
    src_loc: SrcLoc
    is_transaction: bool


@dataclass
class Profile:
    transactions_and_methods: dict[int, ProfileInfo] = field(default_factory=dict)
    waiting_transactions: dict[int, dict[int, int]] = field(default_factory=dict)
    running: dict[int, dict[int, Optional[int]]] = field(default_factory=dict)

    def encode(self, file_name: str):
        with open(file_name, "w") as fp:
            json.dump(self, fp, cls=ProfileJSONEncoder)
