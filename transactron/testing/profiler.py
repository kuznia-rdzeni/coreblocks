from amaranth import Cat
from amaranth.lib.data import StructLayout, View
from amaranth.sim._async import ProcessContext
from transactron.core import TransactionManager
from transactron.core.manager import MethodMap
from transactron.profiler import CycleProfile, MethodSamples, Profile, ProfileData, ProfileSamples, TransactionSamples

__all__ = ["profiler_process"]


def profiler_process(transaction_manager: TransactionManager, profile: Profile):
    async def process(sim: ProcessContext) -> None:
        profile_data, get_id = ProfileData.make(transaction_manager)
        method_map = MethodMap(transaction_manager.transactions)
        profile.transactions_and_methods = profile_data.transactions_and_methods

        transaction_sample_layout = StructLayout({"request": 1, "runnable": 1, "grant": 1})

        async for _, _, *data in (
            sim.tick()
            .sample(
                *(
                    View(transaction_sample_layout, Cat(transaction.request, transaction.runnable, transaction.grant))
                    for transaction in method_map.transactions
                )
            )
            .sample(*(method.run for method in method_map.methods))
        ):
            transaction_data = data[: len(method_map.transactions)]
            method_data = data[len(method_map.transactions) :]
            samples = ProfileSamples()

            for transaction, tsample in zip(method_map.transactions, transaction_data):
                samples.transactions[get_id(transaction)] = TransactionSamples(
                    bool(tsample.request),
                    bool(tsample.runnable),
                    bool(tsample.grant),
                )

            for method, run in zip(method_map.methods, method_data):
                samples.methods[get_id(method)] = MethodSamples(bool(run))

            cprof = CycleProfile.make(samples, profile_data)
            profile.cycles.append(cprof)

    return process
