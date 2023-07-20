
import functools
from collections import defaultdict, deque
from amaranth import *
from collections.abc import Callable, Generator, Iterable
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Generic, Optional, TypeAlias, TypeVar

from amaranth.sim import Settle
from .common import RecordIntDict, TestGen
from coreblocks.transactions.lib import AdapterBase


_T = TypeVar("_T")
TTestGen: TypeAlias = Generator["Action | Exit", Any, _T]
ActionFun: TypeAlias = Callable[[], TestGen[Any] | Any]
Process: TypeAlias = Callable[[], TTestGen[None]]


class ActionKind(Enum):
    GET = auto()
    GET_COMPLETE = auto()
    PUT = auto()
    PUT_FINAL = auto()


@dataclass
class Exit:
    pass


@dataclass
class Action:
    kind: ActionKind
    subject: Any
    action: ActionFun


class SimFIFO(Generic[_T]):
    def __init__(self, init: Iterable[_T] = ()):
        self._queue = deque(init)

    def push(self, value: _T) -> TTestGen[None]:
        def action():
            self._queue.append(value)
        yield Action(ActionKind.PUT_FINAL, self._queue, action)

    def empty(self) -> TTestGen[bool]:
        return (yield Action(ActionKind.GET, self, lambda: bool(self._queue)))

    def peek(self) -> TTestGen[_T]:
        return (yield Action(ActionKind.GET, self, lambda: self._queue[0]))

    def pop(self) -> TTestGen[_T]:
        def complete():
            self._queue.popleft()
        yield Action(ActionKind.GET_COMPLETE, self._queue, complete)
        return (yield Action(ActionKind.GET, self, lambda: self._queue[0]))


class SimSignal(Generic[_T]):
    def __init__(self):
        self._value = None

    def get(self) -> TTestGen[_T]:
        return (yield Action(ActionKind.GET, self, lambda: self._value))

    def set(self, value: _T, *, final: bool = False) -> TTestGen[None]:
        def action():
            self._value = value
        yield Action(ActionKind.PUT_FINAL if final else ActionKind.PUT, self, action)

    def set_final(self, value: _T) -> TTestGen[None]:
        return self.set(value, final=True)


class Sim:
    def __init__(self, processes: Iterable[Callable[[], TTestGen[None]]]):
        self.processes = list(processes)

    def process(self) -> TestGen[None]:
        def run_action(action: ActionFun):
            result = action()
            if isinstance(result, Generator):
                return (yield from result)
            else:
                return result

        process_map = {id(process): process for process in self.processes}

        active = list(map(id, self.processes))

        while active:
            # Set to true when a signal is modified. A settle will be performed before next signal read.
            need_settle = False
            # Maps entity IDs to sets of process IDs which read that entity.
            gets = defaultdict[int, set[int]](set)
            # Maps Values to values read from the Value. Used to decide when to restart processes.
            get_results = dict[Value, int]()
            # Maps entity IDs to single process IDs which write that entity.
            puts = dict[int, int]()
            # Maps process IDs to actions to perform on process completion.
            put_finals = defaultdict[int, list[Action]](list)
            get_completes = defaultdict[int, list[Action]](list)
            exits = set[int]()
            # Which processes were started. If a process needs to be restarted, it is removed from this list.
            already_run = list[int]()
            # Processes ready for execution.
            to_run = deque(active)

            def restart_processes(processes: Iterable[int]):
                nonlocal already_run
                to_run.extend(gets[id(subject)])
                for i in gets[id(subject)]:
                    del put_finals[i]
                    del get_completes[i]
                    exits.remove(i)
                already_run = [i for i in already_run if i not in gets[id(subject)]]

            def perform_settle():
                yield Settle()
                to_restart = set[int]()
                for subject, v in get_results.items():
                    new_v = (yield subject)
                    if new_v != v:
                        get_results[subject] = new_v
                        to_restart.update(gets[id(subject)])
                restart_processes(to_restart)

            while to_run:
                process = to_run.popleft()
                already_run.append(id(process))
                running = process_map[process]()
                to_send = None
                try:
                    while True:
                        cmd = running.send(to_send)
                        match cmd:
                            case Exit():
                                exits.add(id(process))
                                running.close()
                                break
                            case Action(ActionKind.GET, subject, action):
                                gets[id(subject)].add(id(process))
                                if isinstance(subject, Value) and need_settle:
                                    need_settle = False
                                    yield from perform_settle()
                                to_send = (yield from run_action(action))
                                if isinstance(subject, Value):
                                    get_results[subject] = to_send
                            case Action(ActionKind.PUT, subject, action):
                                if id(subject) in puts and puts[id(subject)] != id(process):
                                    raise RuntimeError
                                puts[id(subject)] = id(process)
                                if isinstance(subject, Value):
                                    need_settle = True
                                restart_processes(gets[id(subject)])
                                gets[id(subject)] = set()
                                yield from run_action(action)
                            case Action(ActionKind.PUT_FINAL, subject, action):
                                put_finals[id(process)].append(cmd)
                            case Action(ActionKind.GET_COMPLETE, subject, action):
                                get_completes[id(process)].append(cmd)
                except StopIteration:
                    pass
                if not to_run and need_settle:
                    yield from perform_settle()

            get_completes_subjects = set[int]()
            for i, cmds in get_completes.items():
                for cmd in cmds:
                    if id(cmd.subject) in get_completes_subjects:
                        raise RuntimeError
                    get_completes_subjects.add(id(cmd.subject))
                    yield from run_action(cmd.action)

            for i, cmds in put_finals.items():
                for cmd in cmds:
                    if id(cmd.subject) in puts:
                        raise RuntimeError
                    puts[id(cmd.subject)] = i
                    yield from run_action(cmd.action)

            # In next iteration, run processes in the order they were run in this one.
            # Hopefully this reduces the number of process restarts.
            active = [i for i in already_run if i not in exits]

            yield

    @staticmethod
    def exit() -> TTestGen[Any]:
        yield Exit()

    @staticmethod
    def get(value: Value) -> TTestGen[int]:
        def action():
            return (yield value)
        return (yield Action(ActionKind.GET, value, action))

    @staticmethod
    def set(signal: Signal, value: int, *, final: bool = False) -> TTestGen[None]:
        def action():
            yield signal.eq(value)
        yield Action(ActionKind.PUT_FINAL if final else ActionKind.PUT, signal, action)

    @staticmethod
    def set_final(signal: Signal, value: int) -> TTestGen[None]:
        return Sim.set(signal, value, final=True)


def def_method_mock(
    tb_getter: Callable[[], AdapterBase] | Callable[[Any], AdapterBase]
) -> Callable[[Callable[..., Optional[RecordIntDict]]], Process]:
    def decorator(func: Callable[..., Optional[RecordIntDict]]) -> Process:
        @functools.wraps(func)
        def mock(func_self=None, /):
            f = func
            getter: Any = tb_getter
            if func_self is not None:
                getter = getter.__get__(func_self)
                f = f.__get__(func_self)
            adapter = getter()
            assert isinstance(adapter, AdapterBase)
            
            yield from Sim.set(adapter.en, 1)

        return mock
    return decorator
