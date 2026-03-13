from amaranth.lib import data
from typing import Optional
from amaranth_types import ValueLike
from amaranth import *


class CircularBufferPointer(data.View):
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

    def __add__(self, val: int) -> "CircularBufferPointer":
        return CircularBufferPointer(self.layout, (Cat(self.ptr, self.parity) + val)[: self.layout.ptr_width + 1])

    def __sub__(self, val: int) -> "CircularBufferPointer":
        return CircularBufferPointer(self.layout, (Cat(self.ptr, self.parity) - val)[: self.layout.ptr_width + 1])

    def __lt__(self, other: "CircularBufferPointer") -> Value:
        parity_different = self.parity ^ other.parity
        ptr_smaller = self.ptr < other.ptr
        return parity_different ^ ptr_smaller

    def __le__(self, other: "CircularBufferPointer") -> Value:
        parity_different = self.parity ^ other.parity
        ptr_smaller_equal = self.ptr <= other.ptr
        return parity_different ^ ptr_smaller_equal

    def __ge__(self, other: "CircularBufferPointer") -> Value:
        parity_different = self.parity ^ other.parity
        ptr_smaller_equal = self.ptr >= other.ptr
        return parity_different ^ ptr_smaller_equal

    @staticmethod
    def queue_full(enqueue_ptr: "CircularBufferPointer", dequeue_ptr: "CircularBufferPointer") -> Value:
        return (enqueue_ptr.parity != dequeue_ptr.parity) & (enqueue_ptr.ptr == dequeue_ptr.ptr)

    @staticmethod
    def queue_empty(enqueue_ptr: "CircularBufferPointer", dequeue_ptr: "CircularBufferPointer") -> Value:
        return enqueue_ptr.as_value() == dequeue_ptr.as_value()

    @staticmethod
    def queue_size(enqueue_ptr: "CircularBufferPointer", dequeue_ptr: "CircularBufferPointer") -> Value:
        return (enqueue_ptr.ptr - dequeue_ptr.ptr).as_unsigned()[: enqueue_ptr.layout.ptr_width] + (
            enqueue_ptr.parity ^ dequeue_ptr.parity
        )
