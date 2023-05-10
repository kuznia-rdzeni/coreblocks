from common import *
from typing import TypeVar, overload, Protocol, TypeGuard
from dataclasses import dataclass
from message_queue import *

# TODO add support for @Arusekk syntax trick

__all__ = [
    "MessageFrameworkProcess",
    "TestCaseWithMessageFramework",
    "InternalMessage",
]


class MessageFrameworkCommand:
    pass


class EndOfInput(MessageFrameworkCommand):
    pass


_T_userdata = TypeVar("_T_userdata")


@dataclass
class InternalMessage(Generic[_T_userdata]):
    clk: int
    userdata: _T_userdata


_MFVerificationDataType = MessageFrameworkCommand | InternalMessage[_T_userdata]
T = TypeVar("T")
T1 = TypeVar("T1")
T2 = TypeVar("T2")
T3 = TypeVar("T3")


class ClockProcess:
    def __init__(self):
        self.now: int = 0

    def process(self):
        while True:
            yield
            self.now += 1

def _simple_combiner(x : dict[str,T]) -> T:
    if len(x)==1:
        return list(x.values())[0] 
    else:
        raise RuntimeError("You can use default combiner, only if there is exactly one source.")



_T_userdata_in = TypeVar("_T_userdata_in")
_T_userdata_out = TypeVar("_T_userdata_out")
_T_userdata_transformed = TypeVar("_T_userdata_transformed")


class MessageFrameworkProcess(Generic[_T_userdata_in, _T_userdata_out, _T_userdata_transformed]):
    """
    tb : TestbenchIO
        Method under test
    transformation_in : Callable
        Function used to transform incoming *verification* data
    transformation_out : Callable
        Function used to produce *verification* data for other testing processes
        using as arguments transformed input verification data and test data from
        tested method.
    checker : Callable
        Function to check correctness of test data from method using transformed
        input verification data.
    """

    def __init__(
        self,
        tb: Optional[TestbenchIO],
        *,
        transformation_in: Callable[[_T_userdata_in], _T_userdata_transformed] = lambda x: x,
        transformation_out: Callable[[_T_userdata_transformed, RecordIntDict], _T_userdata_out] = lambda x, y: {},
        prepare_send_data: Callable[[_T_userdata_transformed], RecordIntDictRet] = lambda x: {},
        checker: Callable[[_T_userdata_transformed, RecordIntDict], None] = lambda x, y: None,
    ):
        self.tb = tb

        self.passive = False
        self.transformation_in: Callable[[_T_userdata_in], _T_userdata_transformed] = transformation_in
        self.transformation_out: Callable[
            [_T_userdata_transformed, RecordIntDict], _T_userdata_out
        ] = transformation_out
        self.prepare_send_data: Callable[[_T_userdata_transformed], RecordIntDictRet] = prepare_send_data
        self.checker: Callable[[_T_userdata_transformed, RecordIntDict], None] = checker
        self.iteration_count: Optional[int] = None

    def add_to_simulation(
        self,
        internal_processes: "TestCaseWithMessageFramework.InternalProcesses",
        in_verif_data: MessageQueueInterface[_MFVerificationDataType[_T_userdata_in]],
        out_verif_data: MessageQueueInterface[_MFVerificationDataType[_T_userdata_out]],
    ):
        self.internal = internal_processes
        self.in_verif_data = in_verif_data
        self.out_verif_data = out_verif_data

    @staticmethod
    def _guard_no_transformation_in(
        instance: "MessageFrameworkProcess",
    ) -> TypeGuard["MessageFrameworkProcess"[_T_userdata_in, _T_userdata_out, _T_userdata_in]]:
        if instance.transformation_in is None:
            return True
        return False

    @staticmethod
    def _guard_no_transformation_out(
        instance: "MessageFrameworkProcess",
    ) -> TypeGuard["MessageFrameworkProcess"[_T_userdata_in, _T_userdata_transformed, _T_userdata_transformed]]:
        if instance.transformation_out is None:
            return True
        return False

    def _get_test_data(self, arg_to_send: RecordIntDict):
        if self.tb is not None:
            out_data = yield from self.tb.call(arg_to_send)
            return out_data
        return {}

    def _get_verifcation_input(self) -> TestGen[_MFVerificationDataType]:
        while not self.in_verif_data:
            yield
        return self.in_verif_data.pop()

    def process(self):
        if not (hasattr(self, "in_verif_data") and hasattr(self, "out_verif_data") and hasattr(self, "internal")):
            raise RuntimeError("Simulation started before adding proces to Message Framework.")

        if self.passive:
            yield Passive()
        i = 0
        while self.iteration_count is None or (i < self.iteration_count):
            i += 1
            raw_verif_input = yield from self._get_verifcation_input()
            if isinstance(raw_verif_input, MessageFrameworkCommand):
                if isinstance(raw_verif_input, EndOfInput):
                    break
                raise RuntimeError(f"Got unknown MessageFrameworkCommand: {raw_verif_input}")
            transformed_verif_input = self.transformation_in(raw_verif_input.userdata)
            send_data = self.prepare_send_data(transformed_verif_input)
            test_data = yield from self._get_test_data(send_data)
            self.checker(transformed_verif_input, test_data)
            transformed_output = self.transformation_out(transformed_verif_input, test_data)
            msg = InternalMessage(self.internal.clk.now, transformed_output)
            self.out_verif_data.append(msg)
        self.out_verif_data.append(EndOfInput())


class TestCaseWithMessageFramework(TestCaseWithSimulator):
    @dataclass
    class ProcessEntry:
        proc: MessageFrameworkProcess
        in_combiner: MessageQueueCombiner
        out_broadcaster: MessageQueueBroadcaster

    @dataclass
    class InternalProcesses:
        clk: ClockProcess

    def __init__(self):
        super().__init__()
        self.processes: dict[str, TestCaseWithMessageFramework.ProcessEntry] = {}
        self.internal = TestCaseWithMessageFramework.InternalProcesses(ClockProcess())

    def register_process(self, name: str, proc: MessageFrameworkProcess[T1, Any, T3], *, combiner_f = _simple_combiner ):
        combiner = MessageQueueCombiner[_MFVerificationDataType[T1], Any](combiner=combiner_f)
        broadcaster = MessageQueueBroadcaster[_MFVerificationDataType[T3]]()
        proc.add_to_simulation(self.internal, combiner, broadcaster)
        self.processes[name] = TestCaseWithMessageFramework.ProcessEntry(proc, combiner, broadcaster)

    def _wrap_filter(
        self, f: Optional[Callable[[InternalMessage[_T_userdata]], bool]]
    ) -> Optional[Callable[[_MFVerificationDataType[_T_userdata]], bool]]:
        if f is None:
            return None

        def wraped(input: _MFVerificationDataType) -> bool:
            if isinstance(input, MessageFrameworkCommand):
                return True
            return f(input)

        return wraped

    def add_data_flow(
        self, from_name: str, to_name: str, *, filter: Optional[Callable[[InternalMessage[_T_userdata]], bool]] = None
    ):
        msg_q: MessageQueue[_MFVerificationDataType[_T_userdata]] = MessageQueue(filter=self._wrap_filter(filter))

        proc_from = self.processes[from_name]
        proc_from.out_broadcaster.add_destination(msg_q)

        proc_to = self.processes[to_name]
        proc_to.in_combiner.add_source(msg_q, from_name)

    def start_test(self, module: HasElaborate):
        with self.run_simulation(module) as sim:
            sim.add_sync_process(self.internal.clk.process)
            for p in self.processes.values():
                sim.add_sync_process(p.proc.process)
