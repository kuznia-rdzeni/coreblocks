from abc import ABC, abstractmethod
from collections.abc import Callable
from enum import Enum, IntFlag, auto
from typing import Optional, TypeVar
from dataclasses import dataclass, replace
from elftools.elf.constants import P_FLAGS
from elftools.elf.elffile import ELFFile

all = [
    "ReplyStatus",
    "ReadRequest",
    "ReadReply",
    "WriteRequest",
    "WriteReply",
    "MemoryModel",
    "RAMSegment",
    "CoreMemoryModel",
]


class ReplyStatus(Enum):
    OK = auto()
    ERROR = auto()
    RETRY = auto()


class SegmentFlags(IntFlag):
    READ = auto()
    WRITE = auto()
    EXECUTABLE = auto()


@dataclass
class ReadRequest:
    addr: int
    byte_count: int
    byte_sel: int
    exec: bool


@dataclass
class ReadReply:
    data: int = 0
    status: ReplyStatus = ReplyStatus.OK


@dataclass
class WriteRequest:
    addr: int
    data: int
    byte_count: int
    byte_sel: int


@dataclass
class WriteReply:
    status: ReplyStatus = ReplyStatus.OK


class MemorySegment(ABC):
    def __init__(self, address_range: range, flags: SegmentFlags):
        self.address_range = address_range
        self.flags = flags

    @abstractmethod
    def read(self, req: ReadRequest) -> ReadReply:
        raise NotImplementedError

    @abstractmethod
    def write(self, req: WriteRequest) -> WriteReply:
        raise NotImplementedError


class RandomAccessMemory(MemorySegment):
    def __init__(self, address_range: range, flags: SegmentFlags, data: bytes):
        super().__init__(address_range, flags)
        self.data = bytearray(data)

        if len(self.data) != len(address_range):
            raise ValueError("Data length must be equal to the lenth of the address range")

    def read(self, req: ReadRequest) -> ReadReply:
        return ReadReply(data=int.from_bytes(self.data[req.addr : req.addr + req.byte_count], "little"))

    def write(self, req: WriteRequest) -> WriteReply:
        mask_bytes = [b"\x00", b"\xff"]
        mask = int.from_bytes(b"".join(mask_bytes[1 & (req.byte_sel >> i)] for i in range(4)), "little")
        old = int.from_bytes(self.data[req.addr : req.addr + req.byte_count], "little")
        self.data[req.addr : req.addr + req.byte_count] = (old & ~mask | req.data & mask).to_bytes(4, "little")
        return WriteReply()


TReq = TypeVar("TReq", bound=ReadRequest | WriteRequest)
TRep = TypeVar("TRep", bound=ReadReply | WriteReply)


class CoreMemoryModel:
    def __init__(self, segments: list[MemorySegment], fail_on_undefined=True):
        self.segments = segments
        self.fail_on_undefined = fail_on_undefined

    def _run_on_range(self, f: Callable[[MemorySegment, TReq], TRep], req: TReq) -> Optional[TRep]:
        for seg in self.segments:
            if req.addr in seg.address_range:
                return f(seg, req)

    def _do_read(self, seg: MemorySegment, req: ReadRequest) -> ReadReply:
        if SegmentFlags.READ not in seg.flags:
            raise RuntimeError("Tried to read from non-read memory: %x" % req.addr)
        if req.exec and SegmentFlags.EXECUTABLE not in seg.flags:
            raise RuntimeError("Memory is not executable: %x" % req.addr)

        return seg.read(replace(req, addr=req.addr - seg.address_range.start))

    def _do_write(self, seg: MemorySegment, req: WriteRequest) -> WriteReply:
        if SegmentFlags.READ not in seg.flags:
            raise RuntimeError("Tried to write to non-writable memory: %x" % req.addr)

        return seg.write(replace(req, addr=req.addr - seg.address_range.start))

    def read(self, req: ReadRequest) -> ReadReply:
        rep = self._run_on_range(self._do_read, req)
        if rep is not None:
            return rep
        if self.fail_on_undefined:
            raise RuntimeError("Undefined read: %x" % req.addr)
        else:
            return ReadReply(status=ReplyStatus.ERROR)

    def write(self, req: WriteRequest) -> WriteReply:
        rep = self._run_on_range(self._do_write, req)
        if rep is not None:
            return rep
        if self.fail_on_undefined:
            raise RuntimeError("Undefined write: %x <= %x" % (req.addr, req.data))
        else:
            return WriteReply(status=ReplyStatus.ERROR)


def load_segments_from_elf(file_path: str) -> list[RandomAccessMemory]:
    segments: list[RandomAccessMemory] = []

    with open(file_path, "rb") as f:
        elffile = ELFFile(f)
        for segment in elffile.iter_segments():
            if segment.header["p_type"] != "PT_LOAD":
                continue

            paddr = segment.header["p_paddr"]
            alignment = segment.header["p_align"]
            memsz = segment.header["p_memsz"]
            flags_raw = segment.header["p_flags"]

            def align_down(n: int) -> int:
                return (n // alignment) * alignment

            seg_start = align_down(paddr)
            seg_end = align_down(paddr + memsz + alignment - 1)

            data = b"\x00" * (paddr - seg_start) + segment.data() + b"\x00" * (seg_end - (paddr + len(segment.data())))

            flags = SegmentFlags(0)
            if flags_raw & P_FLAGS.PF_R == flags_raw & P_FLAGS.PF_R:
                flags |= SegmentFlags.READ
            if flags_raw & P_FLAGS.PF_W == flags_raw & P_FLAGS.PF_W:
                flags |= SegmentFlags.WRITE
            if flags_raw & P_FLAGS.PF_X == flags_raw & P_FLAGS.PF_X:
                flags |= SegmentFlags.EXECUTABLE

            segments.append(RandomAccessMemory(range(seg_start, seg_end), flags, data))

    return segments
