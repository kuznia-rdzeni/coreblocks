from abc import ABC, abstractmethod
from collections.abc import Callable
from enum import Enum, IntFlag, auto
from typing import Optional, TypeVar
from dataclasses import dataclass, replace
from elftools.elf.constants import P_FLAGS
from elftools.elf.elffile import ELFFile, Segment
from coreblocks.params.configurations import CoreConfiguration
from transactron.utils import align_to_power_of_two, align_down_to_power_of_two

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
            raise ValueError("Data length must be equal to the length of the address range")

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
    def __init__(self, segments: list[MemorySegment], fail_on_undefined_read=False, fail_on_undefined_write=True):
        self.segments = segments
        self.fail_on_undefined_read = fail_on_undefined_read  # Core may do undefined reads speculatively
        self.fail_on_undefined_write = fail_on_undefined_write

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
        if SegmentFlags.WRITE not in seg.flags:
            raise RuntimeError("Tried to write to non-writable memory: %x" % req.addr)

        return seg.write(replace(req, addr=req.addr - seg.address_range.start))

    def read(self, req: ReadRequest) -> ReadReply:
        rep = self._run_on_range(self._do_read, req)
        if rep is not None:
            return rep
        if self.fail_on_undefined_read:
            raise RuntimeError("Undefined read: %x" % req.addr)
        else:
            return ReadReply(status=ReplyStatus.ERROR)

    def write(self, req: WriteRequest) -> WriteReply:
        rep = self._run_on_range(self._do_write, req)
        if rep is not None:
            return rep
        if self.fail_on_undefined_write:
            raise RuntimeError("Undefined write: %x <= %x" % (req.addr, req.data))
        else:
            return WriteReply(status=ReplyStatus.ERROR)


def load_segment(
    segment: Segment, *, disable_write_protection: bool = False, force_executable: bool = False
) -> RandomAccessMemory:
    paddr = segment.header["p_paddr"]
    memsz = segment.header["p_memsz"]
    flags_raw = segment.header["p_flags"]

    seg_start = paddr
    seg_end = paddr + memsz

    data = segment.data()

    # fill the rest of the segment with zeroes
    data = data + b"\x00" * (seg_end - seg_start - len(data))

    flags = SegmentFlags(0)
    if flags_raw & P_FLAGS.PF_R:
        flags |= SegmentFlags.READ
    if flags_raw & P_FLAGS.PF_W or disable_write_protection:
        flags |= SegmentFlags.WRITE
    if flags_raw & P_FLAGS.PF_X or force_executable:
        flags |= SegmentFlags.EXECUTABLE

    config = CoreConfiguration()
    if flags & SegmentFlags.EXECUTABLE:
        # align instruction section to full icache lines
        align_bits = config.icache_line_bytes_log
        # workaround for fetching/stalling issue
        extend_end = 2**config.icache_line_bytes_log
    else:
        align_bits = 0
        extend_end = 0

    align_data_front = seg_start - align_down_to_power_of_two(seg_start, align_bits)
    align_data_back = align_to_power_of_two(seg_end, align_bits) - seg_end + extend_end

    data = b"\x00" * align_data_front + data + b"\x00" * align_data_back

    seg_start = align_down_to_power_of_two(seg_start, align_bits)
    seg_end = align_to_power_of_two(seg_end, align_bits) + extend_end

    return RandomAccessMemory(range(seg_start, seg_end), flags, data)


def load_segments_from_elf(
    file_path: str, *, disable_write_protection: bool = False, force_executable: bool = False
) -> list[RandomAccessMemory]:
    segments: list[RandomAccessMemory] = []

    with open(file_path, "rb") as f:
        elffile = ELFFile(f)
        for segment in elffile.iter_segments():
            if segment.header["p_type"] != "PT_LOAD" and segment.header["p_type"] != "PT_NULL":
                continue
            segments.append(
                load_segment(
                    segment, disable_write_protection=disable_write_protection, force_executable=force_executable
                )
            )

    return segments
