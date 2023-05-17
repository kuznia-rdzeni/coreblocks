import sys
import random
from typing import TypeVar, TypeGuard, TypeAlias
from dataclasses import dataclass
from contextlib import contextmanager
from collections import deque

from test.common import *

# TODO add support for @Arusekk syntax trick

__all__ = [
    "MessageFrameworkProcessOneSrc",
    "TestCaseWithMessageFramework",
    "InternalMessage",
    "MessageFrameworkCommand",
]


class MessageFrameworkCommand:
    pass


class EndOfInput(MessageFrameworkCommand):
    pass


T = TypeVar("T")
_T_userdata_in = TypeVar("_T_userdata_in")


@dataclass
class InternalMessage(Generic[T]):
    clk: int
    userdata: T


_MFVerificationDataType: TypeAlias = MessageFrameworkCommand | InternalMessage[T]


class ClockProcess:
    def __init__(self):
        self.now: int = 0

    def process(self):
        yield Passive()
        while True:
            yield
            self.now += 1


class StarterProcess:
    def __init__(self, clk: ClockProcess):
        self.clk = clk
        self.proc_to_start: list["MessageFrameworkProcessOneSrc"] = []
        self.callees=set()

    def process(self):
        yield Passive()
        while True:
            yield
            for p in self.proc_to_start:
                p(None)


class MessageFrameworkProcessOneSrc(Generic[_T_userdata_in]):
    def __init__(
        self,
        *,
        tb: Optional[TestbenchIO] = None,
        max_rand_wait=2,
        iteration_count: Optional[int] = None,
        passive: bool = False,
        started: bool = False,
        name: str = "",
        filters: list[Callable[[InternalMessage[_T_userdata_in]], bool]] = [],
    ):
        self.tb = tb
        self.max_rand_wait = max_rand_wait
        self.name = name
        self.passive = passive
        self.iteration_count = iteration_count
        self.filters: list[Callable[[InternalMessage[_T_userdata_in]], bool]] = filters

        self.input_q = deque()
        self.callees: set[MessageFrameworkProcessOneSrc] = set()

        self.tc: "TestCaseWithMessageFramework" = TestCaseWithMessageFramework.stack[-1]
        self.internal = self.tc.internal
        self.tc.processes.append(self)
        if started:
            self.internal.starter.proc_to_start.append(self)

    class RestartMsgProcessing(Exception):
        pass

    def drop(self):
        self.input_q.popleft()

    def handle_raw_data(self, data: InternalMessage[_T_userdata_in]):
        if not all([f(data) for f in self.filters]):
            self.drop()
            raise self.RestartMsgProcessing()
        return data.userdata

    def handle_input_data(self, data):
        return data

    def call_tb(self, input_data):
        out_data = {}
        if self.tb is not None:
            out_data = yield from self.tb.call_try(input_data)
            if out_data is None:
                raise self.RestartMsgProcessing()
            self.drop()
        return input_data, out_data

    def check(self, data):
        return data

    def finish(self, data):
        return

    def random_wait(self):
        cycles = random.randrange(self.max_rand_wait + 1)
        for i in range(cycles):
            yield

    def __call__(self, arg: _T_userdata_in):
        # Do some magic, so that user wouldn't see difference between this and normal function call.
        caller_frame = sys._getframe(1)
        caller = caller_frame.f_locals["self"]
        if not (isinstance(caller, MessageFrameworkProcessOneSrc) or isinstance(caller, StarterProcess)):
            raise RuntimeError(f"Called {self.name} from process different than MessageFrameworkProcessOneSrc.")

        # Register itself to caller to get MessageFrameworkCommands
        if self not in caller.callees:
            caller.callees.add(self)

        packet = InternalMessage[_T_userdata_in](self.internal.clk.now, arg)
        self.input_q.append(packet)

    def get_head(self):
        return self.input_q[0]

    def _get_verifcation_input(self) -> TestGen[_MFVerificationDataType]:
        while not self.input_q:
            yield
        return self.get_head()

    def _receive_command(self, cmd: MessageFrameworkCommand):
        self.input_q.append(cmd)

    def _send_command(self, cmd: MessageFrameworkCommand):
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
                    i -= 1
                    continue
                self.check(data)
                self.finish(data)
                self.random_wait()
            self._send_command(EndOfInput())
        except Exception as e:
            #e.add_note(f"From process: {self.name}")
            raise e


class TestCaseWithMessageFramework(TestCaseWithSimulator):
    stack = []

    @dataclass
    class InternalProcesses:
        clk: ClockProcess
        starter: StarterProcess

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_internal()
        self.processes: list[MessageFrameworkProcessOneSrc] = []

    def _create_internal(self):
        clk = ClockProcess()
        starter = StarterProcess(clk)
        self.internal = TestCaseWithMessageFramework.InternalProcesses(clk, starter)

    @contextmanager
    def prepare_env(self, module: HasElaborate):
        self.stack.append(self)
        with self.run_simulation(module) as sim:
            yield sim
            sim.add_sync_process(self.internal.clk.process)
            sim.add_sync_process(self.internal.starter.process)
            for p in self.processes:
                sim.add_sync_process(p.process)
        self.stack.pop()
