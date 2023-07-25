from abc import ABC, abstractmethod
import functools
import random
from collections import defaultdict, deque
from amaranth import *
from collections.abc import Callable, Coroutine, Generator, Iterable, Mapping
from dataclasses import dataclass, field
from enum import IntEnum, auto
from typing import Any, ClassVar, Concatenate, Generic, Optional, ParamSpec, TypeAlias, TypeVar, cast

from amaranth.sim import Settle
from .common import RecordIntDict, RecordIntDictRet, TestGen
from coreblocks.transactions.lib import AdapterBase
from coreblocks.transactions._utils import method_def_helper


_P = ParamSpec("_P")
_T = TypeVar("_T")
Command: TypeAlias = "Action | Exit | Skip | Wait | Passive | WaitSettled | CycleId"
TTestGen: TypeAlias = Coroutine[Command, Any, _T]
OptSelfCallable: TypeAlias = Callable[_P, _T] | Callable[Concatenate[Any, _P], _T]
OptSelfThing: TypeAlias = Callable[[Any], _T] | _T
ActionFun: TypeAlias = Callable[[], TestGen[Any] | Any]
Process: TypeAlias = Callable[[], TTestGen[None]]


def opt_self_resolve(func_self: Any, func: OptSelfCallable[[], _T]) -> Callable[[], _T]:
    if func_self is None:
        return cast(Any, func)
    else:
        return func.__get__(func_self)


def opt_self_thing_resolve(func_self: Any, thing: OptSelfThing[_T]) -> _T:
    if func_self is None:
        return cast(Any, thing)
    else:
        assert isinstance(thing, Callable)
        return thing(func_self)


class ActionKind(IntEnum):
    GET = auto()
    GET_COMPLETE = auto()
    PUT = auto()
    PUT_FINAL = auto()
    PRINT = auto()
    _YIELD = auto()
    RESET = auto()


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
class Wait(SelfAwaitable):
    pass


@dataclass
class WaitSettled(SelfAwaitable):
    pass


@dataclass
class Passive(SelfAwaitable):
    pass


@dataclass
class CycleId(SelfAwaitable):
    pass


@dataclass
class Action(SelfAwaitable):
    kind: ActionKind
    subject: Any
    action: ActionFun


@dataclass
class ProcessState:
    puts: list[int] = field(default_factory=list)
    exit = False
    passive = False


class SimQueueBase(ABC, Generic[_T]):
    @abstractmethod
    async def not_empty(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def push(self, value: _T) -> None:
        raise NotImplementedError

    @abstractmethod
    async def peek(self) -> _T:
        raise NotImplementedError

    @abstractmethod
    async def pop(self) -> _T:
        raise NotImplementedError

    async def empty(self) -> bool:
        return not await self.not_empty()

    async def pop_or_exit(self) -> _T:
        if await self.empty():
            await Exit()
        return await self.pop()

    async def pop_or_skip(self) -> _T:
        if await self.empty():
            await Skip()
        return await self.pop()


class SimFIFO(SimQueueBase[_T]):
    def __init__(self, init: Iterable[_T] = ()):
        self._queue = deque(init)

    def __bool__(self):
        raise TypeError("Attempted to convert SimFIFO to boolean")

    def init_push(self, value: _T) -> None:
        if Sim._is_running:
            raise RuntimeError("SimFifo.init_push should not be used inside simulation")
        self._queue.append(value)

    async def push(self, value: _T) -> None:
        def action():
            self._queue.append(value)

        await Action(ActionKind.PUT_FINAL, self, action)

    async def not_empty(self) -> bool:
        return await Action(ActionKind.GET, self, lambda: bool(self._queue))

    async def peek(self) -> _T:
        return await Action(ActionKind.GET, self, lambda: self._queue[0])

    async def pop(self) -> _T:
        def complete():
            self._queue.popleft()

        await Action(ActionKind.GET_COMPLETE, self, complete)
        return await self.peek()


class SimSignal(Generic[_T]):
    def __init__(self, init: _T):
        self._value = init

    def __bool__(self):
        raise TypeError("Attempted to convert SimSignal to boolean")

    async def get(self) -> _T:
        return await Action(ActionKind.GET, self, lambda: self._value)

    async def set(self, value: _T, *, final: bool = False) -> None:
        def action():
            self._value = value

        await Action(ActionKind.PUT_FINAL if final else ActionKind.PUT, self, action)

    async def set_final(self, value: _T) -> None:
        await self.set(value, final=True)


class SimPipe(SimQueueBase[_T]):
    def __init__(self):
        self._value = SimSignal[Optional[_T]](None)
        self._can_push = SimSignal(True)

    def __bool__(self):
        raise TypeError("Attempted to convert SimPipe to boolean")

    async def push(self, value: _T) -> None:
        if not await self._can_push.get():
            await Skip()
        await self._value.set_final(value)
        await self._can_push.set_final(False)

    async def not_empty(self) -> bool:
        return await self._value.get() is not None

    async def peek(self) -> _T:
        value = await self._value.get()
        if value is None:
            raise RuntimeError("Peek on empty SimPipe")
        return value

    async def pop(self) -> _T:
        def clear_action():
            self._value._value = None

        await self._can_push.set(True)
        await Action(ActionKind.GET_COMPLETE, self._value, clear_action)
        return await self.peek()


class SimRandomDelay:
    def __init__(self, max_delay: int):
        self.max_delay = max_delay
        self._counter = SimSignal[int](random.randint(0, max_delay))

    def __bool__(self):
        raise TypeError("Attempted to convert SimRandomDelay to boolean")

    async def should_wait(self) -> bool:
        val = await self._counter.get()
        if val:
            await self._counter.set_final(val - 1)
            return True
        else:
            await self._counter.set_final(random.randint(0, self.max_delay))
            return False

    async def wait(self) -> None:
        if await self.should_wait():
            await Skip()


class Sim:
    _is_running: ClassVar[bool] = False

    def __init__(self, processes: Iterable[Process] = ()):
        self.processes = list(processes)

    def add_process(self, process: Process):
        self.processes.append(process)

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
        cycle_id = 0

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
            last_things = defaultdict[int, list[tuple[ActionKind, Action]]](list)
            # Various data about effects performed by processes
            states = defaultdict[int, ProcessState](ProcessState)
            # Processes ready for execution.
            to_run = deque[tuple[int, TTestGen[None]]]()
            # Suspended processes.
            suspended = dict[int, TTestGen[None]]()
            suspended_settled = dict[int, TTestGen[None]]()
            # In settled phase, PUT actions are rejected.
            settled = False

            def schedule(processes: Iterable[int]):
                to_run.extend((process, process_map[process]()) for process in processes)

            def restart_processes(processes: set[int]):
                schedule(processes)
                for i in processes:
                    if i in states:
                        for j in states[i].puts:
                            del puts[j]
                        del states[i]
                    if i in last_things:
                        del last_things[i]
                    if i in suspended:
                        suspended[i].close()
                        del suspended[i]

            def perform_settle():
                yield Settle()
                to_restart = set[int]()
                for subject, (value, v) in get_results.items():
                    new_v = yield value
                    if new_v != v:
                        get_results[subject] = (value, new_v)
                        to_restart.update(gets[subject])
                restart_processes(to_restart)

            schedule(active)

            while to_run:
                process, running = to_run.popleft()
                to_send = None
                try:
                    while True:
                        Sim._is_running = True
                        cmd = running.send(to_send)
                        Sim._is_running = False

                        match cmd:
                            case Passive():
                                states[process].passive = True
                            case Skip():
                                last_things[process] = [
                                    (kind, action)
                                    for (kind, action) in last_things[process]
                                    if kind not in [ActionKind.GET_COMPLETE]
                                ]
                                running.close()
                                break
                            case Wait():
                                suspended[process] = running
                                break
                            case WaitSettled():
                                if not settled:
                                    suspended_settled[process] = running
                                    break
                            case Exit():
                                states[process].exit = True
                                running.close()
                                break
                            case CycleId():
                                to_send = cycle_id
                            case Action(ActionKind.GET, subject, action):
                                gets[id(subject)].add(process)
                                if isinstance(subject, Value) and need_settle:
                                    need_settle = False
                                    yield from perform_settle()
                                to_send = yield from run_action(action)
                                if isinstance(subject, Value):
                                    get_results[id(subject)] = (subject, to_send)
                            case Action(ActionKind.PUT, subject, action):
                                if settled:
                                    raise RuntimeError(f"PUT on {subject} during settled phase")
                                if id(subject) in puts:
                                    raise RuntimeError
                                puts[id(subject)] = process
                                states[process].puts.append(id(subject))
                                if isinstance(subject, Value):
                                    need_settle = True
                                restart_processes(gets[id(subject)])
                                gets[id(subject)] = set()
                                yield from run_action(action)
                            case Action(
                                ActionKind.PUT_FINAL
                                | ActionKind.GET_COMPLETE
                                | ActionKind.PRINT
                                | ActionKind.RESET as kind,
                                subject,
                                action,
                            ):
                                last_things[process].append((kind, cmd))
                except StopIteration:
                    pass
                if not to_run and need_settle:
                    yield from perform_settle()
                if not to_run and suspended:
                    to_run.extend(suspended.items())
                    suspended = {}
                if not to_run and suspended_settled:
                    to_run.extend(suspended_settled.items())
                    suspended_settled = {}
                    settled = True

            last_things_list = list[tuple[ActionKind, int, Action]]()

            def yield_action():
                yield

            last_things[id(self)].append((ActionKind._YIELD, Action(ActionKind._YIELD, self, yield_action)))

            for process, things in last_things.items():
                for kind, cmd in things:
                    last_things_list.append((kind, process, cmd))

            last_things_list.sort(key=lambda k: k[0])

            subjects_for_kind = {ActionKind.GET_COMPLETE: dict[int, int](), ActionKind.PUT_FINAL: puts}

            for kind, process, cmd in last_things_list:
                if kind in subjects_for_kind:
                    if id(cmd.subject) in subjects_for_kind[kind]:
                        raise RuntimeError(f"Action {str(kind)} performed twice on {cmd.subject}")
                    subjects_for_kind[kind][id(cmd.subject)] = process
                yield from run_action(cmd.action)

            active = [i for i in active if not states[i].exit]
            run = any(not states[i].passive for i in active)
            cycle_id = cycle_id + 1

    @staticmethod
    async def exit() -> Any:
        await Exit()

    @staticmethod
    async def skip() -> Any:
        await Skip()

    @staticmethod
    async def passive() -> Any:
        await Passive()

    @staticmethod
    async def print(text: str) -> None:
        return await Action(ActionKind.PRINT, None, lambda: print(text))

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
    async def reset(signal: Signal, value: int) -> None:
        def action():
            yield signal.eq(value)

        await Action(ActionKind.RESET, signal, action)

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
    async def set_record(rec: Record, values: RecordIntDict, *, final: bool = False) -> None:
        for name, value in values.items():
            if isinstance(value, Mapping):
                await Sim.set_record(getattr(rec, name), value, final=final)
            else:
                await Sim.set(getattr(rec, name), value, final=final)

    @staticmethod
    async def call_try(
        adapter: AdapterBase, data: RecordIntDict = {}, /, **kwdata: int | RecordIntDict
    ) -> Optional[RecordIntDictRet]:
        if data and kwdata:
            raise TypeError("call() takes either a single dict or keyword arguments")
        if not data:
            data = kwdata

        await Sim.set(adapter.en, 1)
        await Sim.reset(adapter.en, 0)
        await Sim.set_record(adapter.data_in, data)
        await Wait()
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
        tb_getter: OptSelfCallable[[], AdapterBase],
        *,
        enable: Optional[OptSelfCallable[[], TTestGen[bool]]] = None,
        active: Optional[OptSelfCallable[[], TTestGen[bool]]] = None,
        enabled_active: bool = False,
        max_delay: int = 0,
    ) -> Callable[[Callable[..., TTestGen[Optional[RecordIntDict]]]], Process]:
        def decorator(func: Callable[..., TTestGen[Optional[RecordIntDict]]]) -> Process:
            if max_delay:
                random_delay = SimRandomDelay(max_delay)

            @functools.wraps(func)
            async def mock(func_self=None, /):
                r_func = opt_self_resolve(func_self, func)
                r_getter = opt_self_resolve(func_self, tb_getter)
                r_enable = opt_self_resolve(func_self, enable) if enable is not None else None
                r_active = opt_self_resolve(func_self, active) if active is not None else None

                adapter = r_getter()
                assert isinstance(adapter, AdapterBase)

                enabled = r_enable is None or await r_enable()
                stay_active = r_active is not None and await r_active()
                should_wait = max_delay and await random_delay.should_wait()

                if not stay_active and (not enabled or not enabled_active):
                    await Passive()

                if not enabled or should_wait:
                    return

                await Sim.set(adapter.en, 1)
                await Sim.reset(adapter.en, 0)
                await Wait()
                if await Sim.get(adapter.done):
                    arg = await Sim.get_record(adapter.data_out)
                    res = await method_def_helper(adapter, r_func, **arg)
                    await Sim.set_record(adapter.data_in, res or {})

            return mock

        return decorator

    @staticmethod
    def with_random_delay(max_delay: int):
        def decorator(func: Callable[..., TTestGen[None]]):
            random_delay = SimRandomDelay(max_delay)

            @functools.wraps(func)
            async def process(func_self=None, /):
                r_func = opt_self_resolve(func_self, func)
                await random_delay.wait()
                await r_func()

            return process

        return decorator

    @staticmethod
    def queue_reader(*queues: OptSelfThing[SimQueueBase], max_delay: int = 0):
        def decorator(func: Callable[..., TTestGen[None]]):
            if max_delay:
                random_delay = SimRandomDelay(max_delay)

            @functools.wraps(func)
            async def process(func_self=None, /):
                r_func = opt_self_resolve(func_self, func)

                args = []
                for queue in queues:
                    r_queue = opt_self_thing_resolve(func_self, queue)
                    if await r_queue.not_empty():
                        args.append(await r_queue.pop())

                # Ending simulation possible only when queues empty
                if not args:
                    await Passive()

                if len(args) < len(queues):
                    await Skip()

                if max_delay:
                    await random_delay.wait()

                await r_func(*args)

            return process

        return decorator
