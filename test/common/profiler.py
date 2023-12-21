import json
from typing import Optional
from dataclasses import dataclass, field, is_dataclass, asdict
from amaranth.sim import *
from transactron.core import MethodMap, TransactionManager, Transaction, Method
from transactron.lib import SrcLoc
from .functions import TestGen

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
    def process() -> TestGen:
        method_map = MethodMap(transaction_manager.transactions)
        cgr, _, _ = TransactionManager._conflict_graph(method_map)
        id_map = dict[int, int]()
        id_seq = 0

        def get_id(obj):
            try:
                return id_map[id(obj)]
            except KeyError:
                nonlocal id_seq
                id_seq = id_seq + 1
                id_map[id(obj)] = id_seq
                return id_seq

        for transaction in method_map.transactions:
            profile.transactions_and_methods[get_id(transaction)] = ProfileInfo(
                transaction.owned_name, transaction.src_loc, True
            )

        for method in method_map.methods:
            profile.transactions_and_methods[get_id(method)] = ProfileInfo(method.name, method.src_loc, False)

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
                    profile.running[cycle][get_id(transaction)] = None
                elif request and runnable:
                    for transaction2 in cgr[transaction]:
                        if (yield transaction2.grant):
                            profile.waiting_transactions[cycle][get_id(transaction)] = get_id(transaction2)

            for method in method_map.methods:
                if (yield method.run):
                    for t_or_m in method_map.method_parents[method]:
                        if (
                            isinstance(t_or_m, Transaction)
                            and (yield t_or_m.grant)
                            or isinstance(t_or_m, Method)
                            and (yield t_or_m.run)
                        ):
                            profile.running[cycle][get_id(method)] = get_id(t_or_m)

            yield
            cycle = cycle + 1

    return process
