from amaranth.sim import *
from transactron.core import MethodMap, TransactionManager
from transactron.profiler import CycleProfile, MethodSamples, Profile, ProfileData, ProfileSamples, TransactionSamples
from .functions import TestGen

__all__ = ["profiler_process"]


def profiler_process(transaction_manager: TransactionManager, profile: Profile):
    def process() -> TestGen:
        profile_data, get_id = ProfileData.make(transaction_manager)
        method_map = MethodMap(transaction_manager.transactions)
        profile.transactions_and_methods = profile_data.transactions_and_methods

        yield Passive()
        while True:
            yield Tick("sync_neg")

            transactions = dict[int, TransactionSamples]()
            methods = dict[int, MethodSamples]()

            for transaction in method_map.transactions:
                transactions[get_id(transaction)] = TransactionSamples(
                    bool((yield transaction.request)),
                    bool((yield transaction.runnable)),
                    bool((yield transaction.grant)),
                )

            for method in method_map.methods:
                methods[get_id(method)] = MethodSamples(bool((yield method.run)))

            samples = ProfileSamples(transactions, methods)
            cprof = CycleProfile.make(samples, profile_data)
            profile.cycles.append(cprof)

            yield

    return process
