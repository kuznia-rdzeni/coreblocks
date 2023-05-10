import random
from common import *
from typing import TypeVar, overload, Protocol, TypeGuard
from dataclasses import dataclass
from message_queue import *

# TODO add support for @Arusekk syntax trick

__all__ = [
    "MessageFrameworkProcess",
    "MessageFrameworkExternalAccess",
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
        yield Passive()
        while True:
            yield
            self.now += 1

class StarterProcess:
    def __init__(self, clk : ClockProcess, out_broadcaster : MessageQueueBroadcaster[_MFVerificationDataType[None]]):
        self.clk = clk
        self.out_broadcaster = out_broadcaster

    def process(self):
        yield Passive()
        while True:
            yield
            # Add only if there is a little number of messages to not waste memory during tests.
            # This process will be ready every cycle, but normal test process will be ready one for few
            # cycles so without this "if" we will be genreting more messages than will be ever able to consume
            if len(self.out_broadcaster) < 3:
                self.out_broadcaster.append(InternalMessage(self.clk.now, None))


def _default_combiner(arg : dict[str,T]) -> T:
    if len(arg)==1:
        return list(arg.values())[0] 
    else:
        raise RuntimeError("You can use default combiner, only if there is exactly one source.")



_T_userdata_in = TypeVar("_T_userdata_in")
_T_userdata_out = TypeVar("_T_userdata_out")
_T_userdata_transformed = TypeVar("_T_userdata_transformed")

class MessageFrameworkExternalAccess(Generic[_T_userdata_in, _T_userdata_out]):
    def __init__( self):
        pass

    def add_to_simulation(
        self,
        internal_processes: "TestCaseWithMessageFramework.InternalProcesses",
        in_verif_data: MessageQueueInterface[_MFVerificationDataType[_T_userdata_in]],
        out_verif_data: MessageQueueInterface[_MFVerificationDataType[_T_userdata_out]],
    ):
        self.internal = internal_processes
        self.in_verif_data = in_verif_data
        self.out_verif_data = out_verif_data

    def get(self) -> _T_userdata_in:
        val = self.in_verif_data.pop()
        while isinstance(val,MessageFrameworkCommand):
            val = self.in_verif_data.pop()
        return val.userdata

    def put(self, val : _T_userdata_out):
        msg = InternalMessage(self.internal.clk.now, val)
        self.out_verif_data.append(msg)

class MessageFrameworkProcess(Generic[_T_userdata_in, _T_userdata_transformed, _T_userdata_out]):
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
        max_rand_wait = 2
    ):
        self.tb = tb
        self.max_rand_wait = max_rand_wait

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

    def _random_wait(self):
        cycles = random.randrange(self.max_rand_wait+1)
        for i in range(cycles):
            yield

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
            self._random_wait()
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
    class AccessEntry:
        proc: MessageFrameworkExternalAccess
        in_combiner: MessageQueueCombiner
        out_broadcaster: MessageQueueBroadcaster

    @dataclass
    class InternalProcesses:
        clk: ClockProcess
        starter : StarterProcess

    def __init__(self):
        super().__init__()
        self.processes: dict[str, TestCaseWithMessageFramework.ProcessEntry] = {}
        self.accessors: dict[str, TestCaseWithMessageFramework.AccessEntry] = {}

    def _create_internal(self):
        clk = ClockProcess()
        starter = StarterProcess(clk, MessageQueueBroadcaster())
        self.internal = TestCaseWithMessageFramework.InternalProcesses(clk, starter)

    def register_process(self, name: str, proc: MessageFrameworkProcess[T1, Any, T3], *, combiner_f = _default_combiner ):
        combiner = MessageQueueCombiner[_MFVerificationDataType[T1], Any](combiner=combiner_f)
        broadcaster = MessageQueueBroadcaster[_MFVerificationDataType[T3]]()
        proc.add_to_simulation(self.internal, combiner, broadcaster)
        self.processes[name] = TestCaseWithMessageFramework.ProcessEntry(proc, combiner, broadcaster)

    def register_accessor(self, name: str, proc: MessageFrameworkExternalAccess[T1, T2], *, combiner_f = _default_combiner ):
        combiner = MessageQueueCombiner[_MFVerificationDataType[T1], Any](combiner=combiner_f)
        broadcaster = MessageQueueBroadcaster[_MFVerificationDataType[T2]]()
        self.accessors[name] = TestCaseWithMessageFramework.AccessEntry(proc, combiner, broadcaster)

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

    def _raise_if_process_not_exist(self, name : str):
        if name not in self.processes:
            raise RuntimeError(f"Tried to use not yet registrated process with name: {name}")

    def add_data_flow(
        self, from_name: str, to_name: str, *, filter: Optional[Callable[[InternalMessage[_T_userdata]], bool]] = None
    ):
        self._raise_if_process_not_exist(from_name)
        self._raise_if_process_not_exist(to_name)
        msg_q: MessageQueue[_MFVerificationDataType[_T_userdata]] = MessageQueue(filter=self._wrap_filter(filter))

        if from_name=="starter":
            proc_from = self.internal.starter
        else:
            proc_from = self.processes[from_name]
        proc_from.out_broadcaster.add_destination(msg_q)

        proc_to = self.processes[to_name]
        proc_to.in_combiner.add_source(msg_q, from_name)

    def start_test(self, module: HasElaborate):
        with self.run_simulation(module) as sim:
            sim.add_sync_process(self.internal.clk.process)
            for p in self.processes.values():
                sim.add_sync_process(p.proc.process)
