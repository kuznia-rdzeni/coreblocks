from collections import deque
from abc import abstractmethod, ABC
from typing import TypeVar, Generic, Callable, Optional

__all__ = [
    "MessageQueueInterface",
    "MessageQueueCombiner",
    "MessageQueueBroadcaster",
    "MessageQueue",
]

T = TypeVar("T")
T2 = TypeVar("T2")


class MessageQueueInterface(ABC, Generic[T]):
    @abstractmethod
    def __bool__(self) -> bool:
        pass

    @abstractmethod
    def __len__(self) -> int:
        pass

    @abstractmethod
    def append(self, val: T):
        pass

    @abstractmethod
    def pop(self) -> T:
        pass


class MessageQueueCombiner(MessageQueueInterface[T], Generic[T, T2]):
    def __init__(self, *, combiner: Callable[[dict[str, T2]], T] = lambda x: x):
        self.sources: dict[str, MessageQueueInterface[T2]] = {}
        self.combiner = combiner

    def __bool__(self):
        return all([bool(src) for src in self.sources.values()])

    def __len__(self):
        return min([len(src) for src in self.sources.values()])

    def add_source(self, src: MessageQueueInterface, src_name: str):
        self.sources[src_name] = src

    def append(self, val: T):
        raise NotImplementedError("MessageQueueCombiner doesn't support append")

    def pop(self) -> T:
        return self.combiner(dict((name, src.pop()) for (name, src) in self.sources.items()))


class MessageQueueBroadcaster(MessageQueueInterface[T]):
    def __init__(self):
        self.destinations: list[MessageQueueInterface] = []

    def __bool__(self):
        return all([bool(dst) for dst in self.destinations])

    def __len__(self):
        return min([len(dst) for dst in self.destinations])

    def add_destination(self, dst: MessageQueueInterface):
        self.destinations.append(dst)

    def append(self, val: T):
        for dst in self.destinations:
            dst.append(val)

    def pop(self):
        raise NotImplementedError("MessageQueueBroadcaster doesn't support pop")


class MessageQueue(MessageQueueInterface, Generic[T]):
    def __init__(self, *, filter: Optional[Callable[[T], bool]] = None):
        self.q: deque[T] = deque()
        self.filter = filter

    def _discard_not_ok(self) -> None:
        if self.filter is None:
            return
        while self.q and (not self.filter(self.q[0])):
            self.q.popleft()

    def __bool__(self):
        self._discard_not_ok()
        return bool(self.q)

    def __len__(self):
        return len(self.q)

    def append(self, val: T):
        if self.filter is not None:
            if self.filter(val):
                self.q.append(val)
        else:
            self.q.append(val)

    def pop(self) -> T:
        self._discard_not_ok()
        return self.q.popleft()
