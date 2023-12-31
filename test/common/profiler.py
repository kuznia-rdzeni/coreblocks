from amaranth.sim import *
from transactron.core import MethodMap, TransactionManager, Transaction, Method
from transactron.profiler import CycleProfile, Profile, ProfileInfo
from .functions import TestGen

__all__ = ["profiler_process"]


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
            # TODO: wait for the end of cycle
            for _ in range(3):
                yield Settle()

            cprof = CycleProfile()

            for transaction in method_map.transactions:
                request = yield transaction.request
                runnable = yield transaction.runnable
                grant = yield transaction.grant

                if grant:
                    cprof.running[get_id(transaction)] = None
                elif request and runnable:
                    for transaction2 in cgr[transaction]:
                        if (yield transaction2.grant):
                            cprof.waiting_transactions[get_id(transaction)] = get_id(transaction2)

            for method in method_map.methods:
                if (yield method.run):
                    for t_or_m in method_map.method_parents[method]:
                        if (
                            isinstance(t_or_m, Transaction)
                            and (yield t_or_m.grant)
                            or isinstance(t_or_m, Method)
                            and (yield t_or_m.run)
                        ):
                            cprof.running[get_id(method)] = get_id(t_or_m)
                else:
                    if any(
                        get_id(transaction) in cprof.running
                        for transaction in method_map.transactions_by_method[method]
                    ):
                        cprof.locked_methods.add(get_id(method))

            yield
            cycle = cycle + 1

    return process
