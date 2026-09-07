from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Optional, TypeVar
from dataclasses import replace

from .memory import (
    CoreMemoryModel,
    MMIOSegment,
    MemorySegment,
    RandomAccessMemory,
    ReadReply,
    ReadRequest,
    ReplyStatus,
    SegmentFlags,
    WriteReply,
    WriteRequest,
)

__all__ = [
    "SegmentEmulation",
    "RAMEmulation",
    "MMIOEmulation",
    "CoreMemoryEmulation",
]


class SegmentEmulation(ABC):
    """Emulates the behaviour of a memory segment in Python.

    Request addresses are relative to the start of the segment.
    """

    @abstractmethod
    def read(self, req: ReadRequest) -> ReadReply:
        raise NotImplementedError

    @abstractmethod
    def write(self, req: WriteRequest) -> WriteReply:
        raise NotImplementedError


class RAMEmulation(SegmentEmulation):
    """Byte-addressable storage."""

    def __init__(self, data: bytes):
        self.data = bytearray(data)

    def read(self, req: ReadRequest) -> ReadReply:
        return ReadReply(data=int.from_bytes(self.data[req.addr : req.addr + req.byte_count], "little"))

    def write(self, req: WriteRequest) -> WriteReply:
        mask_bytes = [b"\x00", b"\xff"]
        mask = int.from_bytes(b"".join(mask_bytes[1 & (req.byte_sel >> i)] for i in range(4)), "little")
        old = int.from_bytes(self.data[req.addr : req.addr + req.byte_count], "little")
        self.data[req.addr : req.addr + req.byte_count] = (old & ~mask | req.data & mask).to_bytes(4, "little")
        return WriteReply()


class MMIOEmulation(SegmentEmulation):
    """MMIO segments handle accesses in Python themselves, using the same protocol."""

    def __init__(self, segment: MMIOSegment):
        self.segment = segment

    def read(self, req: ReadRequest) -> ReadReply:
        return self.segment.read(req)

    def write(self, req: WriteRequest) -> WriteReply:
        return self.segment.write(req)


def _emulate_segment(segment: MemorySegment) -> SegmentEmulation:
    """Realizes a segment description in Python."""
    match segment:
        case RandomAccessMemory():
            return RAMEmulation(segment.contents)
        case MMIOSegment():
            return MMIOEmulation(segment)
        case _:
            raise RuntimeError(f"Cannot emulate {type(segment).__name__} in Python")


TReq = TypeVar("TReq", bound=ReadRequest | WriteRequest)
TRep = TypeVar("TRep", bound=ReadReply | WriteReply)


class CoreMemoryEmulation:
    def __init__(self, model: CoreMemoryModel):
        self.model = model
        self.emulations = [_emulate_segment(segment) for segment in model.segments]

    def _run_on_range(self, f: Callable[[MemorySegment, SegmentEmulation, TReq], TRep], req: TReq) -> Optional[TRep]:
        for seg, emulation in zip(self.model.segments, self.emulations):
            if req.addr in seg.address_range:
                return f(seg, emulation, req)

    def _do_read(self, seg: MemorySegment, emulation: SegmentEmulation, req: ReadRequest) -> ReadReply:
        if SegmentFlags.READ not in seg.flags:
            raise RuntimeError("Tried to read from non-read memory: %x" % req.addr)
        if req.exec and SegmentFlags.EXECUTABLE not in seg.flags:
            raise RuntimeError("Memory is not executable: %x" % req.addr)

        return emulation.read(replace(req, addr=req.addr - seg.address_range.start))

    def _do_write(self, seg: MemorySegment, emulation: SegmentEmulation, req: WriteRequest) -> WriteReply:
        if SegmentFlags.WRITE not in seg.flags:
            raise RuntimeError("Tried to write to non-writable memory: %x" % req.addr)

        return emulation.write(replace(req, addr=req.addr - seg.address_range.start))

    def read(self, req: ReadRequest) -> ReadReply:
        rep = self._run_on_range(self._do_read, req)
        if rep is not None:
            return rep
        if self.model.fail_on_undefined_read:
            raise RuntimeError("Undefined read: %x" % req.addr)
        else:
            return ReadReply(status=ReplyStatus.ERROR)

    def write(self, req: WriteRequest) -> WriteReply:
        rep = self._run_on_range(self._do_write, req)
        if rep is not None:
            return rep
        if self.model.fail_on_undefined_write:
            raise RuntimeError("Undefined write: %x <= %x" % (req.addr, req.data))
        else:
            return WriteReply(status=ReplyStatus.ERROR)
