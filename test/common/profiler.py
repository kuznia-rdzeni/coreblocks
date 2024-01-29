import os.path
from amaranth.sim import *
from transactron.core import MethodMap, TransactionManager
from transactron.profiler import CycleProfile, Profile, ProfileInfo
from transactron.utils import SrcLoc
from .functions import TestGen

__all__ = ["profiler_process"]


def profiler_process(transaction_manager: TransactionManager, profile: Profile, clk_period: float):
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

        def local_src_loc(src_loc: SrcLoc):
            return (os.path.relpath(src_loc[0]), src_loc[1])

        for transaction in method_map.transactions:
            profile.transactions_and_methods[get_id(transaction)] = ProfileInfo(
                transaction.owned_name, local_src_loc(transaction.src_loc), True
            )

        for method in method_map.methods:
            profile.transactions_and_methods[get_id(method)] = ProfileInfo(
                method.owned_name, local_src_loc(method.src_loc), False
            )

        yield Passive()
        while True:
            yield Delay((1 - 1e-4) * clk_period)  # shorter than one clock cycle

            cprof = CycleProfile()
            profile.cycles.append(cprof)

            for transaction in method_map.transactions:
                request = yield transaction.request
                runnable = yield transaction.runnable
                grant = yield transaction.grant

                if grant:
                    cprof.running[get_id(transaction)] = None
                elif request and runnable:
                    for transaction2 in cgr[transaction]:
                        if (yield transaction2.grant):
                            cprof.locked[get_id(transaction)] = get_id(transaction2)

            running = set(cprof.running)
            for method in method_map.methods:
                if (yield method.run):
                    running.add(get_id(method))

            locked_methods = set[int]()
            for method in method_map.methods:
                if get_id(method) not in running:
                    if any(get_id(transaction) in running for transaction in method_map.transactions_by_method[method]):
                        locked_methods.add(get_id(method))

            for method in method_map.methods:
                if get_id(method) in running:
                    for t_or_m in method_map.method_parents[method]:
                        if get_id(t_or_m) in running:
                            cprof.running[get_id(method)] = get_id(t_or_m)
                elif get_id(method) in locked_methods:
                    caller = next(
                        get_id(t_or_m)
                        for t_or_m in method_map.method_parents[method]
                        if get_id(t_or_m) in running or get_id(t_or_m) in locked_methods
                    )
                    cprof.locked[get_id(method)] = caller

            yield

    return process
