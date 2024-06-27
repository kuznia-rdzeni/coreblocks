from typing import Optional

from amaranth import *
from amaranth.lib import data

from transactron.utils._typing import ValueLike

__all__ = ["CircularQueuePtr"]


class CircularQueuePtr(data.View):
    class Layout(data.StructLayout):
        def __init__(self, size_log: int):
            super().__init__(
                {
                    "ptr": size_log,
                    "parity": 1,
                }
            )

            self.ptr_width = size_log

    def __init__(self, layout: Layout, target: Optional[ValueLike] = None, **kwargs):
        super().__init__(layout=layout, target=target if target is not None else Signal(layout), **kwargs)

        self.layout = layout

    def __add__(self, val: int) -> "CircularQueuePtr":
        return CircularQueuePtr(self.layout, (Cat(self.ptr, self.parity) + val)[: self.layout.ptr_width + 1])

    def __sub__(self, val: int) -> "CircularQueuePtr":
        return CircularQueuePtr(self.layout, (Cat(self.ptr, self.parity) - val)[: self.layout.ptr_width + 1])

    def __lt__(self, other: "CircularQueuePtr") -> Value:
        parity_different = self.parity ^ other.parity
        ptr_smaller = self.ptr < other.ptr
        return parity_different ^ ptr_smaller

    def __le__(self, other: "CircularQueuePtr") -> Value:
        parity_different = self.parity ^ other.parity
        ptr_smaller_equal = self.ptr <= other.ptr
        return parity_different ^ ptr_smaller_equal

    @staticmethod
    def queue_full(enqueue_ptr: "CircularQueuePtr", dequeue_ptr: "CircularQueuePtr") -> Value:
        return (enqueue_ptr.parity != dequeue_ptr.parity) & (enqueue_ptr.ptr == dequeue_ptr.ptr)

    @staticmethod
    def queue_empty(enqueue_ptr: "CircularQueuePtr", dequeue_ptr: "CircularQueuePtr") -> Value:
        return enqueue_ptr.as_value() == dequeue_ptr.as_value()
