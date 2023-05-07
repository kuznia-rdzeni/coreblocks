from collections import deque
from abc import abstractmethod, ABC
from typing import TypeVar, Generic

__all__ =[
        "MessageQueueInterface",
        "MessageQueueCombiner",
        "MessageQueueBroadcaster",
        "MessageQueue",
        ]

T = TypeVar('T')

class MessageQueueInterface(ABC, Generic[T]):
    @abstractmethod
    def append(self, val : T):
        pass

    @abstractmethod
    def pop(self) -> T:
        pass

class MessageQueueCombiner(MessageQueueInterface):
    def __init__(self):
        self.sources : list[MessageQueueInterface] = []

    def add_source(self, src : MessageQueueInterface):
        self.sources.append(src)

    def append(self, val):
        raise NotImplementedError("MessageQueueCombiner doesn't support append")

    def pop(self):
        return [src.pop() for src in self.sources]

class MessageQueueBroadcaster(MessageQueueInterface):
    def __init__(self):
        self.destinations : list[MessageQueueInterface] = []

    def add_destination(self, dst : MessageQueueInterface):
        self.destinations.append(dst)

    def append(self, val):
        for dst in self.destinations:
            dst.append(val) 

    def pop(self):
        raise NotImplementedError("MessageQueueBroadcaster doesn't support pop")

class MessageQueue(MessageQueueInterface):
    def __init__(self):
        self.q : deque = deque()

    def append(self, val):
        self.q.append(val)

    def pop(self):
        return self.q.popleft()
