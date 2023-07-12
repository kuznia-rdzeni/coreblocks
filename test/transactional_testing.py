
from collections import defaultdict, deque
from amaranth import *
from collections.abc import Callable, Generator, Iterable
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Generic, Optional, TypeAlias, TypeVar

from amaranth.sim import Settle
from .common import TestGen


_T = TypeVar("_T")
TTestGen: TypeAlias = Generator["Action | Exit", Any, _T]
ActionFun: TypeAlias = Callable[[], TestGen[Any] | Any]


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
        exited = set[int]()

        # TODO nie zadziała!
        # Sygnały mogą się zmieniać po settlu. Trzeba pamiętać, jakie były wartości
        # dla ostatnich odczytów, i restartować te procesy, którym odczyty się zmieniły.

        while active:
            need_settle = False
            gets = defaultdict[int, set[int]](set)
            puts = dict[int, int]()
            put_finals = defaultdict[int, list[Action]](list)
            get_completes = defaultdict[int, list[Action]](list)
            already_run = list[int]()
            to_run = deque(active)

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
                                exited.add(id(process))
                                break
                            case Action(ActionKind.GET, subject, action):
                                gets[id(subject)].add(id(process))
                                if isinstance(subject, Value) and need_settle:
                                    yield Settle()
                                    need_settle = False
                                to_send = (yield from run_action(action))
                            case Action(ActionKind.PUT, subject, action):
                                if id(subject) in puts and puts[id(subject)] != id(process):
                                    raise RuntimeError
                                puts[id(subject)] = id(process)
                                if isinstance(subject, Value):
                                    need_settle = True
                                to_run.extend(gets[id(subject)])
                                for i in gets[id(subject)]:
                                    del put_finals[i]
                                    del get_completes[i]
                                already_run = [i for i in already_run if i not in gets[id(subject)]]
                                gets[id(subject)] = set()
                                yield from run_action(action)
                            case Action(ActionKind.PUT_FINAL, subject, action):
                                put_finals[id(process)].append(cmd)
                            case Action(ActionKind.GET_COMPLETE, subject, action):
                                get_completes[id(process)].append(cmd)
                except StopIteration:
                    pass

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

            active = already_run

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
