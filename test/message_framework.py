import sys
import random
from typing import TypeVar, TypeGuard
from dataclasses import dataclass
from contextlib import contextmanager
from collections import deque

from test.common import *

# TODO add support for @Arusekk syntax trick

__all__ = [
    "MessageFrameworkProcessOneSrc",
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
    def __init__(self, clk: ClockProcess, out_broadcaster: MessageQueueBroadcaster[_MFVerificationDataType[None]]):
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


def _default_combiner(arg: dict[str, T]) -> T:
    if len(arg) == 1:
        return list(arg.values())[0]
    else:
        raise RuntimeError("You can use default combiner, only if there is exactly one source.")


_T_userdata_in = TypeVar("_T_userdata_in")
_T_userdata_out = TypeVar("_T_userdata_out")
_T_userdata_transformed = TypeVar("_T_userdata_transformed")


class MessageFrameworkProcessOneSrc(Generic[_T_userdata_in]):
    def __init__(
        self,
        *,
        tb: Optional[TestbenchIO] = None,
        max_rand_wait=2,
        iteration_count : Optional[int] = None,
        passive : bool = False,
        name : str = ""
    ):
        self.tb = tb
        self.max_rand_wait = max_rand_wait
        self.name = name

        self.passive = passive
        self.iteration_count = iteration_count
        self.filters :list[Callable[[InternalMessage[_T_userdata_in]], bool]] = []
        self.input_q = deque()
        self.callees : set[MessageFrameworkProcessOneSrc] = set()

    def add_to_simulation(
        self,
        internal_processes: "TestCaseWithMessageFramework.InternalProcesses",
    ):
        self.internal = internal_processes

    class RestartMsgProcessing(Exception):
        pass

    def drop(self):
        self.input_q.popleft()

    def handle_raw_data(self, data : InternalMessage[_T_userdata_in]):
        if not all([f(data) for f in self.filters]):
            self.drop()
            raise self.RestartMsgProcessing()
        return data.userdata

    def handle_input_data(self, data):
        return data

    def call_tb(self, send_data):
        out_data = {}
        if self.tb is not None:
            out_data = yield from self.tb.call_try(send_data)
            if out_data is None:
                raise self.RestartMsgProcessing()
            self.drop()
        return send_data, out_data

    def check(self, data):
        return data

    def finish(self, data):
        return

    def random_wait(self):
        cycles = random.randrange(self.max_rand_wait + 1)
        for i in range(cycles):
            yield

    def __call__(self, arg : _T_userdata_in):
        # Do some magic, so that user wouldn't see difference between this and normal function call.
        caller_frame = sys._getframe(1)
        caller = caller_frame.f_locals["self"]
        if not isinstance(caller, MessageFrameworkProcessOneSrc):
            raise RuntimeError(f"Called {self.name} from process different than MessageFrameworkProcessOneSrc.")

        # Register itself to caller to get MessageFrameworkCommands
        if self not in caller.callees:
            caller.callees.add(self)

        packet = InternalMessage[_T_userdata_in](self.internal.clk.now, arg)
        self.input_q.append(packet)

    def _get_verifcation_input(self) -> TestGen[_MFVerificationDataType]:
        while not self.input_q:
            yield
        return self.input_q[0]

    def _receive_command(self, cmd : MessageFrameworkCommand):
        self.input_q.append(cmd)

    def _send_command(self, cmd : MessageFrameworkCommand):
        for c in self.callees:
            c._receive_command(cmd)

    def process(self):
        try:
            if self.passive:
                yield Passive()
            i = 0
            while self.iteration_count is None or (i < self.iteration_count):
                i += 1
                try:
                    raw_verif_input = yield from self._get_verifcation_input()
                    if isinstance(raw_verif_input, MessageFrameworkCommand):
                        if isinstance(raw_verif_input, EndOfInput):
                            break
                        raise RuntimeError(f"Got unknown MessageFrameworkCommand: {raw_verif_input}")
                    data = self.handle_raw_data(raw_verif_input)
                    data = self.handle_input_data(data)
                    data = yield from self.call_tb(data)
                except self.RestartMsgProcessing:
                    i-=1
                    continue
                self.check(data)
                self.finish(data)
                self.random_wait()
            print(f"Koniec procesu {self.name}")
            self._send_command(EndOfInput())
        except Exception as e:
            e.add_note(f"From process: {self.name}")
            raise e


class TestCaseWithMessageFramework(TestCaseWithSimulator):
    @dataclass
    class ProcessEntry:
        proc: MessageFrameworkProcess
        in_combiner: MessageQueueCombiner
        out_broadcaster: MessageQueueBroadcaster

    @dataclass
    class InternalProcesses:
        clk: ClockProcess
        starter: StarterProcess

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.processes: dict[str, TestCaseWithMessageFramework.ProcessEntry] = {}
        self._create_internal()

    def _create_internal(self):
        clk = ClockProcess()
        starter = StarterProcess(clk, MessageQueueBroadcaster())
        self.internal = TestCaseWithMessageFramework.InternalProcesses(clk, starter)

    def register_process(self, name: str, proc: MessageFrameworkProcess[T1, Any, T3], *, combiner_f=_default_combiner):
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

    def _raise_if_process_not_exist(self, name: str):
        known_processes = {"starter"} | set(self.processes.keys()) | set(self.accessors.keys())
        if name not in known_processes:
            raise RuntimeError(f"Tried to use not yet registrated process with name: {name}")

    def _get_process_by_name(self, name: str) -> Union['TestCaseWithMessageFramework.ProcessEntry', 'TestCaseWithMessageFramework.AccessEntry']:
        if name in self.processes:
            return self.processes[name]
        if name in self.accessors:
            return self.accessors[name]
        raise RuntimeError("Process name not known.")

    def add_data_flow(
        self, from_name: str, to_name: str, *, filter: Optional[Callable[[InternalMessage[_T_userdata]], bool]] = None
    ):
        self._raise_if_process_not_exist(from_name)
        self._raise_if_process_not_exist(to_name)
        msg_q: MessageQueue[_MFVerificationDataType[_T_userdata]] = MessageQueue(filter=self._wrap_filter(filter))

        if from_name == "starter":
            proc_from = self.internal.starter
        else:
            proc_from = self._get_process_by_name(from_name)
        proc_from.out_broadcaster.add_destination(msg_q)

        proc_to = self._get_process_by_name(to_name)
        proc_to.in_combiner.add_source(msg_q, from_name)

    @contextmanager
    def prepare_env(self, module: HasElaborate):
        with self.run_simulation(module) as sim:
            yield sim
            sim.add_sync_process(self.internal.clk.process)
            sim.add_sync_process(self.internal.starter.process)
            for p in self.processes.values():
                sim.add_sync_process(p.proc.process)
