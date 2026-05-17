from __future__ import annotations

import os
import sys
import re
from pathlib import Path

from .memory import (
    CoreMemoryModel,
    MemorySegment,
    ReadReply,
    ReadRequest,
    ReplyStatus,
    SegmentFlags,
    WriteReply,
    WriteRequest,
    load_segments_from_elf,
)


ENDTEST_ADDRESS = 0xF0000000
CONSOLE_ADDRESS = 0xF0001000
ACCESS_FAULT_ADDRESS = 0x00000010

ZIFENCEI_PATTERN = re.compile("zifencei", re.IGNORECASE)


class EndTestMMIO(MemorySegment):
    def __init__(self, on_finish):
        super().__init__(range(ENDTEST_ADDRESS, ENDTEST_ADDRESS + 8), SegmentFlags.WRITE)
        self.on_finish = on_finish
        self.written_value = 0

    def read(self, req: ReadRequest) -> ReadReply:
        return ReadReply()

    def write(self, req: WriteRequest) -> WriteReply:
        value = 0
        for index in range(req.byte_count):
            if (req.byte_sel >> index) & 1:
                value |= ((req.data >> (8 * index)) & 0xFF) << (8 * index)

        self.written_value = value
        self.on_finish()
        return WriteReply()


class ConsoleMMIO(MemorySegment):
    def __init__(self):
        super().__init__(range(CONSOLE_ADDRESS, CONSOLE_ADDRESS + 8), SegmentFlags.WRITE)

    def read(self, req: ReadRequest) -> ReadReply:
        return ReadReply()

    def write(self, req: WriteRequest) -> WriteReply:
        data = int(req.data)
        data_bytes = data.to_bytes(req.byte_count, "little", signed=False)
        output = bytes(data_bytes[index] for index in range(req.byte_count) if (req.byte_sel >> index) & 1)
        if not output:
            output = data_bytes

        sys.stdout.buffer.write(output)
        sys.stdout.buffer.flush()
        return WriteReply()


class AccessFaultAddressMMIO(MemorySegment):
    def __init__(self):
        super().__init__(
            range(ACCESS_FAULT_ADDRESS, ACCESS_FAULT_ADDRESS + 8),
            SegmentFlags.READ | SegmentFlags.WRITE | SegmentFlags.EXECUTABLE,
        )

    def read(self, req: ReadRequest) -> ReadReply:
        return ReadReply(status=ReplyStatus.ERROR)

    def write(self, req: WriteRequest) -> WriteReply:
        return WriteReply(status=ReplyStatus.ERROR)


def build_memory_model(elf_path: str | Path, stop_callback, **kwargs) -> tuple[CoreMemoryModel, EndTestMMIO]:
    segments = []
    segments.extend(load_segments_from_elf(str(elf_path), **kwargs))
    segments.append(ConsoleMMIO())
    segments.append(AccessFaultAddressMMIO())
    endtest = EndTestMMIO(stop_callback)
    segments.append(endtest)
    return CoreMemoryModel(segments), endtest


async def run_arch_elf(sim_backend, elf_path: str | Path, timeout_cycles: int = 2_000_000):
    os.environ.setdefault("__TRANSACTRON_LOG_LEVEL", "WARNING")
    os.environ.setdefault("__TRANSACTRON_LOG_FILTER", ".*")

    elf_path = Path(elf_path).resolve()

    mem_model, endtest = build_memory_model(
        elf_path,
        sim_backend.stop,
        disable_write_protection=ZIFENCEI_PATTERN.search(elf_path.name) is not None,
    )

    result = await sim_backend.run(mem_model, timeout_cycles=timeout_cycles)

    assert result.success
    assert endtest.written_value == 1
