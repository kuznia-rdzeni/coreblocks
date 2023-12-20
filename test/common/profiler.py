import json
from typing import Optional
from dataclasses import dataclass, field, is_dataclass, asdict
from transactron.core import MethodMap, TransactionManager, Transaction, Method
from transactron.lib import SrcLoc
from amaranth.sim import *

__all__ = ["profiler_process"]


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


def profiler_process(transaction_manager: TransactionManager, profile: Profile):
    method_map = MethodMap(transaction_manager.transactions)
    cgr, _, _ = TransactionManager._conflict_graph(method_map)

    for transaction in method_map.transactions:
        profile.transactions_and_methods[id(transaction)] = ProfileInfo(
            transaction.owned_name, transaction.src_loc, True
        )

    for method in method_map.methods:
        profile.transactions_and_methods[id(method)] = ProfileInfo(method.name, method.src_loc, False)

    cycle = 0

    yield Passive()
    while True:
        yield Settle()

        profile.waiting_transactions[cycle] = {}
        profile.running[cycle] = {}

        for transaction in method_map.transactions:
            request = yield transaction.request
            runnable = yield transaction.runnable
            grant = yield transaction.grant

            if grant:
                profile.running[cycle][id(transaction)] = None
            elif request and runnable:
                for transaction2 in cgr[transaction]:
                    if (yield transaction2.grant):
                        profile.waiting_transactions[cycle][id(transaction)] = id(transaction2)

        for method in method_map.methods:
            if (yield method.run):
                for t_or_m in method_map.method_parents[method]:
                    if (
                        isinstance(t_or_m, Transaction)
                        and (yield t_or_m.grant)
                        or isinstance(t_or_m, Method)
                        and (yield t_or_m.run)
                    ):
                        profile.running[cycle][id(method)] = id(t_or_m)

        yield
        cycle = cycle + 1
