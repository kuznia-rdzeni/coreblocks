from abc import ABC, abstractmethod
from enum import Enum, IntFlag, auto
from dataclasses import dataclass
from elftools.elf.constants import P_FLAGS
from elftools.elf.elffile import ELFFile, Segment

__all__ = [
    "ReplyStatus",
    "SegmentFlags",
    "ReadRequest",
    "ReadReply",
    "WriteRequest",
    "WriteReply",
    "MemorySegment",
    "RandomAccessMemory",
    "MMIOSegment",
    "CoreMemoryModel",
    "load_segment",
    "load_segments_from_elf",
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


@dataclass
class MemorySegment:
    """Describes a range of the address space."""

    address_range: range
    flags: SegmentFlags


@dataclass
class RandomAccessMemory(MemorySegment):
    """Plain memory, described by its initial contents."""

    contents: bytes

    def __post_init__(self):
        if len(self.contents) != len(self.address_range):
            raise ValueError("Data length must be equal to the length of the address range")


class MMIOSegment(MemorySegment, ABC):
    """A segment whose accesses are handled by Python code, on any backend.

    Request addresses are relative to the start of the segment.
    """

    @abstractmethod
    def read(self, req: ReadRequest) -> ReadReply:
        raise NotImplementedError

    @abstractmethod
    def write(self, req: WriteRequest) -> WriteReply:
        raise NotImplementedError


@dataclass
class CoreMemoryModel:
    """The memory map of the core: the segments, plus the policy for accesses which
    fall outside all of them.
    """

    segments: list[MemorySegment]
    # The core may do undefined reads speculatively
    fail_on_undefined_read: bool = False
    fail_on_undefined_write: bool = True


def load_segment(
    segment: Segment,
    *,
    disable_write_protection: bool = False,
    force_executable: bool = False,
) -> RandomAccessMemory:
    paddr = segment.header["p_paddr"]
    memsz = segment.header["p_memsz"]
    flags_raw = segment.header["p_flags"]

    seg_start = paddr
    seg_end = paddr + memsz

    assert seg_start % 0x40 == 0, f"Segment start {seg_start:#x} is not 64-byte-aligned"
    assert seg_end % 0x40 == 0, f"Segment end {seg_end:#x} is not 64-byte-aligned"

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

    return RandomAccessMemory(range(seg_start, seg_end), flags, data)


def load_segments_from_elf(
    file_path: str,
    *,
    disable_write_protection: bool = False,
    force_executable: bool = False,
) -> list[RandomAccessMemory]:
    segments: list[RandomAccessMemory] = []

    with open(file_path, "rb") as f:
        elffile = ELFFile(f)
        for segment in elffile.iter_segments():
            if segment.header["p_type"] != "PT_LOAD" and segment.header["p_type"] != "PT_NULL":
                continue
            segments.append(
                load_segment(
                    segment,
                    disable_write_protection=disable_write_protection,
                    force_executable=force_executable,
                )
            )

    return segments
