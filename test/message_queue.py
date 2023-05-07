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


class MessageQueueInterface(ABC, Generic[T]):
    @abstractmethod
    def __bool__(self) -> bool:
        pass

    @abstractmethod
    def append(self, val: T):
        pass

    @abstractmethod
    def pop(self) -> T:
        pass


class MessageQueueCombiner(MessageQueueInterface):
    def __init__(self):
        self.sources: list[MessageQueueInterface] = []

    def __bool__(self):
        return all([bool(src) for src in self.sources])

    def add_source(self, src: MessageQueueInterface):
        self.sources.append(src)

    def append(self, val):
        raise NotImplementedError("MessageQueueCombiner doesn't support append")

    def pop(self):
        return [src.pop() for src in self.sources]


class MessageQueueBroadcaster(MessageQueueInterface):
    def __init__(self):
        self.destinations: list[MessageQueueInterface] = []

    def __bool__(self):
        return False

    def add_destination(self, dst: MessageQueueInterface):
        self.destinations.append(dst)

    def append(self, val):
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

    def append(self, val : T):
        if self.filter is not None:
            if self.filter(val):
                self.q.append(val)
        else:
            self.q.append(val)

    def pop(self) -> T:
        self._discard_not_ok()
        return self.q.popleft()
