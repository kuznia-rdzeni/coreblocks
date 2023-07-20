import functools
from collections import defaultdict, deque
from amaranth import *
from collections.abc import Callable, Coroutine, Generator, Iterable, Mapping
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Generic, Optional, TypeAlias, TypeVar, cast

from amaranth.sim import Settle
from .common import RecordIntDict, RecordIntDictRet, TestGen
from coreblocks.transactions.lib import AdapterBase
from coreblocks.transactions._utils import method_def_helper


_T = TypeVar("_T")
TTestGen: TypeAlias = Coroutine["Action | Exit | Skip | Passive", Any, _T]
OptSelfCallable: TypeAlias = Callable[[], _T] | Callable[[Any], _T]
ActionFun: TypeAlias = Callable[[], TestGen[Any] | Any]
Process: TypeAlias = Callable[[], TTestGen[None]]


def opt_self_resolve(func_self: Any, func: OptSelfCallable[_T]) -> Callable[[], _T]:
    if func_self is None:
        return cast(Any, func)
    else:
        return func.__get__(func_self)


class ActionKind(Enum):
    GET = auto()
    GET_COMPLETE = auto()
    PUT = auto()
    PUT_FINAL = auto()


class SelfAwaitable:
    def __await__(self):
        return (yield self)


@dataclass
class Exit(SelfAwaitable):
    pass


@dataclass
class Skip(SelfAwaitable):
    pass


@dataclass
class Passive(SelfAwaitable):
    pass


@dataclass
class Action(SelfAwaitable):
    kind: ActionKind
    subject: Any
    action: ActionFun


class SimFIFO(Generic[_T]):
    def __init__(self, init: Iterable[_T] = ()):
        self._queue = deque(init)

    async def push(self, value: _T) -> None:
        def action():
            self._queue.append(value)

        await Action(ActionKind.PUT_FINAL, self._queue, action)

    async def empty(self) -> bool:
        return await Action(ActionKind.GET, self, lambda: not self._queue)

    async def peek(self) -> _T:
        return await Action(ActionKind.GET, self, lambda: self._queue[0])

    async def pop(self) -> _T:
        def complete():
            self._queue.popleft()

        await Action(ActionKind.GET_COMPLETE, self._queue, complete)
        return await Action(ActionKind.GET, self, lambda: self._queue[0])

    async def pop_or_exit(self) -> _T:
        if await self.empty():
            await Exit()
        return await self.pop()


class SimSignal(Generic[_T]):
    def __init__(self):
        self._value = None

    async def get(self) -> _T:
        return await Action(ActionKind.GET, self, lambda: self._value)

    async def set(self, value: _T, *, final: bool = False) -> None:
        def action():
            self._value = value

        await Action(ActionKind.PUT_FINAL if final else ActionKind.PUT, self, action)

    async def set_final(self, value: _T) -> None:
        await self.set(value, final=True)


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
        run = bool(active)

        while run:
            # Set to true when a signal is modified. A settle will be performed before next signal read.
            need_settle = False
            # Maps entity IDs to sets of process IDs which read that entity.
            gets = defaultdict[int, set[int]](set)
            # Maps Value IDs to values read from the Value. Used to decide when to restart processes.
            get_results = dict[int, tuple[Value, int]]()
            # Maps entity IDs to single process IDs which write that entity.
            puts = dict[int, int]()
            # Maps process IDs to actions to perform on process completion.
            put_finals = defaultdict[int, list[Action]](list)
            get_completes = defaultdict[int, list[Action]](list)
            exits = set[int]()
            passives = set[int]()
            # Which processes were started. If a process needs to be restarted, it is removed from this list.
            already_run = list[int]()
            # Processes ready for execution.
            to_run = deque(active)

            def restart_processes(processes: set[int]):
                nonlocal already_run
                to_run.extend(processes)
                for i in processes:
                    if i in put_finals:
                        del put_finals[i]
                    if i in get_completes:
                        del get_completes[i]
                    if i in exits:
                        exits.remove(i)
                    if i in passives:
                        passives.remove(i)
                already_run = [i for i in already_run if i not in processes]

            def perform_settle():
                yield Settle()
                to_restart = set[int]()
                for subject, (value, v) in get_results.items():
                    new_v = yield value
                    if new_v != v:
                        get_results[subject] = (value, new_v)
                        to_restart.update(gets[subject])
                restart_processes(to_restart)

            while to_run:
                process = to_run.popleft()
                already_run.append(process)
                running = process_map[process]()
                to_send = None
                try:
                    while True:
                        cmd = running.send(to_send)
                        match cmd:
                            case Passive():
                                passives.add(process)
                            case Skip():
                                running.close()
                                break
                            case Exit():
                                exits.add(process)
                                running.close()
                                break
                            case Action(ActionKind.GET, subject, action):
                                gets[id(subject)].add(process)
                                if isinstance(subject, Value) and need_settle:
                                    need_settle = False
                                    yield from perform_settle()
                                to_send = yield from run_action(action)
                                if isinstance(subject, Value):
                                    get_results[id(subject)] = (subject, to_send)
                            case Action(ActionKind.PUT, subject, action):
                                if id(subject) in puts and puts[id(subject)] != process:
                                    raise RuntimeError
                                puts[id(subject)] = process
                                if isinstance(subject, Value):
                                    need_settle = True
                                restart_processes(gets[id(subject)])
                                gets[id(subject)] = set()
                                yield from run_action(action)
                            case Action(ActionKind.PUT_FINAL, subject, action):
                                put_finals[process].append(cmd)
                            case Action(ActionKind.GET_COMPLETE, subject, action):
                                get_completes[process].append(cmd)
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

            run = any(i not in passives for i in active)

            yield

    @staticmethod
    async def exit() -> Any:
        yield Exit()

    @staticmethod
    async def get(value: Value) -> int:
        def action():
            return (yield value)

        return await Action(ActionKind.GET, value, action)

    @staticmethod
    async def set(signal: Signal, value: int, *, final: bool = False) -> None:
        def action():
            yield signal.eq(value)

        await Action(ActionKind.PUT_FINAL if final else ActionKind.PUT, signal, action)

    @staticmethod
    async def set_final(signal: Signal, value: int) -> None:
        await Sim.set(signal, value, final=True)

    @staticmethod
    async def get_record(rec: Record) -> RecordIntDict:
        result = {}
        for name, _, _ in rec.layout:
            val = getattr(rec, name)
            if isinstance(val, Signal):
                result[name] = await Sim.get(val)
            else:  # field is a Record
                result[name] = await Sim.get_record(val)
        return result

    @staticmethod
    async def set_record(rec: Record, values: RecordIntDict) -> None:
        for name, value in values.items():
            if isinstance(value, Mapping):
                await Sim.set_record(getattr(rec, name), value)
            else:
                await Sim.set(getattr(rec, name), value)

    @staticmethod
    async def call_try(
        adapter: AdapterBase, data: RecordIntDict = {}, /, **kwdata: int | RecordIntDict
    ) -> Optional[RecordIntDictRet]:
        if data and kwdata:
            raise TypeError("call() takes either a single dict or keyword arguments")
        if not data:
            data = kwdata

        await Sim.set(adapter.en, 1)
        await Sim.set_record(adapter.data_in, data)
        if await Sim.get(adapter.done):
            return await Sim.get_record(adapter.data_out)
        else:
            return None

    @staticmethod
    async def call(
        adapter: AdapterBase, data: RecordIntDict = {}, /, **kwdata: int | RecordIntDict
    ) -> RecordIntDictRet:
        result = await Sim.call_try(adapter, data, **kwdata)
        if result is None:
            await Skip()
            assert False
        else:
            return result

    @staticmethod
    def def_method_mock(
        tb_getter: OptSelfCallable[AdapterBase], *, enable: Optional[OptSelfCallable[TTestGen[bool]]] = None
    ) -> Callable[[Callable[..., TTestGen[Optional[RecordIntDict]]]], Process]:
        def decorator(func: Callable[..., TTestGen[Optional[RecordIntDict]]]) -> Process:
            @functools.wraps(func)
            async def mock(func_self=None, /):
                r_func = opt_self_resolve(func_self, func)
                r_getter = opt_self_resolve(func_self, tb_getter)
                r_enable = opt_self_resolve(func_self, enable) if enable is not None else None

                adapter = r_getter()
                assert isinstance(adapter, AdapterBase)

                await Passive()

                if r_enable is not None and not await r_enable():
                    await Sim.set(adapter.en, 0)
                    return

                await Sim.set(adapter.en, 1)
                if await Sim.get(adapter.done):
                    arg = await Sim.get_record(adapter.data_out)
                    res = await method_def_helper(adapter, r_func, **arg)
                    await Sim.set_record(adapter.data_in, res or {})

            return mock

        return decorator
