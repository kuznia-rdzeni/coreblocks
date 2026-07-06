"""Converter from captured event logs to the Kanata pipeline-visualization
format (https://github.com/shioyadan/Konata).

Since Kanata files are append-only with monotonically increasing time, and
the concrete instructions of a fetch block are only known when they leave
the fetch unit, the converter buffers everything: event handlers build
per-instruction stage timelines, and the log is written out at the end,
sorted by cycle. This allows backdating an instruction's fetch stages to
the times its fetch block was allocated and requested.
"""

import argparse
import signal
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Optional, TextIO
import capstone

from transactron.evlog import DecodedEvent, EventConsumer, EventLogReader, handles

from .events import (
    ExecComplete,
    FetchRequest,
    FTQAlloc,
    FTQCommit,
    FTQRollback,
    FuIssue,
    InstrDecoded,
    InstrFetched,
    RobAllocate,
    RobFlush,
    RobRetire,
    SchedulerEnter,
)


__all__ = ["KonataParser"]


@dataclass
class _Block:
    """A fetch block owned by a live FTQ entry, buffered until its concrete
    instructions are known."""

    pc: int
    fetch_cycle: Optional[int] = None
    instr_ids: dict[int, int] = field(default_factory=dict)
    """Kanata instruction ids, keyed by the FTQ offset."""


class KonataParser(EventConsumer):
    """Converts instruction lifetime events into a Kanata log.

    An instruction's lifetime starts at the fetch request for its fetch
    block. Stages:

    - "F" from the fetch request until the instruction leaves the fetch unit,
    - "Q" while it waits in the frontend instruction queue,
    - "D" from landing in the decode stage,
    - "Rn" (rename) from entering the scheduler,
    - "Ds" (dispatch) from ROB allocation (which is where the
      instruction becomes identified by its ROB id),
    - "Is" (issue) from being issued to a functional unit,
    - "Cm" once execution completes.

    The instruction terminates by retiring (`RobRetire`) or being squashed.
    Instructions still in flight when the event log ends are left unterminated.
    """

    def __init__(self, out: TextIO):
        self.out = out
        # Live FTQ entries, keyed by the raw FTQ pointer (with the parity
        # bit, which makes keys unique among live entries); insertion order
        # is allocation order.
        self.blocks: dict[int, _Block] = {}
        # Kanata instruction ids of live ROB entries, keyed by the ROB id.
        self.rob: dict[int, int] = {}
        # Kanata instruction ids with a terminal (retire/flush) record.
        self.terminated: set[int] = set()
        # (cycle, sequence number, line) command timeline; the sequence
        # number keeps the append order among commands of the same cycle.
        self.timeline: list[tuple[int, int, str]] = []
        self.next_id = 0
        self.next_retire_id = 0
        self.disassembler = None

        # The fetch unit expands compressed instructions, so plain RV32
        # is enough to disassemble the (expanded) instruction words.
        self.disassembler = capstone.Cs(capstone.CS_ARCH_RISCV, capstone.CS_MODE_RISCV32)

    def _format_instr(self, pc: int, instr: int) -> str:
        if self.disassembler is not None:
            for disasm in self.disassembler.disasm(instr.to_bytes(4, "little"), pc):
                return f"{disasm.mnemonic} {disasm.op_str}".strip()
        return f"{instr:08x}"

    def run(self, records: Iterable[DecodedEvent]):
        super().run(records)
        self._write()

    def _command(self, cycle: int, *columns) -> None:
        self.timeline.append((cycle, len(self.timeline), "\t".join(str(col) for col in columns)))

    @handles(FTQAlloc)
    def on_alloc(self, rec: DecodedEvent):
        ev = rec.event
        assert isinstance(ev, FTQAlloc)
        # The allocation itself is not visualized (the FTQ entry's lifetime
        # differs from the instructions'), but the entry must be tracked so
        # that commits and rollbacks cover it.
        self.blocks[ev.ftq_ptr] = _Block(pc=ev.pc)

    @handles(FetchRequest)
    def on_fetch_request(self, rec: DecodedEvent):
        ev = rec.event
        assert isinstance(ev, FetchRequest)
        block = self.blocks.setdefault(ev.ftq_ptr, _Block(pc=ev.pc))
        block.fetch_cycle = rec.cycle

    @handles(InstrFetched)
    def on_instr_fetched(self, rec: DecodedEvent):
        ev = rec.event
        assert isinstance(ev, InstrFetched)
        block = self.blocks.setdefault(ev.ftq_ptr, _Block(pc=ev.pc))

        insn_id = self.next_id
        self.next_id += 1
        block.instr_ids[ev.ftq_offset] = insn_id

        start = block.fetch_cycle if block.fetch_cycle is not None else rec.cycle

        self._command(start, "I", insn_id, insn_id, 0)
        self._command(start, "L", insn_id, 0, f"{ev.pc:08x}: {self._format_instr(ev.pc, ev.instr)}")
        self._command(start, "L", insn_id, 1, f"instr={ev.instr:08x} ftq_ptr={ev.ftq_ptr} ftq_offset={ev.ftq_offset}")
        self._command(start, "S", insn_id, 0, "F")
        self._command(rec.cycle, "S", insn_id, 0, "Q")

    @handles(InstrDecoded)
    def on_instr_decoded(self, rec: DecodedEvent):
        ev = rec.event
        assert isinstance(ev, InstrDecoded)
        block = self.blocks.get(ev.ftq_ptr)
        if block is None or ev.ftq_offset not in block.instr_ids:
            return
        self._command(rec.cycle, "S", block.instr_ids[ev.ftq_offset], 0, "D")

    @handles(SchedulerEnter)
    def on_scheduler_enter(self, rec: DecodedEvent):
        ev = rec.event
        assert isinstance(ev, SchedulerEnter)
        block = self.blocks.get(ev.ftq_ptr)
        if block is None or ev.ftq_offset not in block.instr_ids:
            return
        self._command(rec.cycle, "S", block.instr_ids[ev.ftq_offset], 0, "Rn")

    @handles(RobAllocate)
    def on_rob_allocate(self, rec: DecodedEvent):
        ev = rec.event
        assert isinstance(ev, RobAllocate)
        block = self.blocks.get(ev.ftq_ptr)
        if block is None or ev.ftq_offset not in block.instr_ids:
            return
        insn_id = block.instr_ids[ev.ftq_offset]
        self.rob[ev.rob_id] = insn_id
        self._command(rec.cycle, "S", insn_id, 0, "Ds")
        self._command(rec.cycle, "L", insn_id, 1, f" rob_id={ev.rob_id}")

    @handles(FuIssue)
    def on_fu_issue(self, rec: DecodedEvent):
        ev = rec.event
        assert isinstance(ev, FuIssue)
        insn_id = self.rob.get(ev.rob_id)
        if insn_id is None or insn_id in self.terminated:
            return
        self._command(rec.cycle, "S", insn_id, 0, "Is")
        self._command(rec.cycle, "L", insn_id, 1, f" fu={ev.unit}")

    @handles(ExecComplete)
    def on_exec_complete(self, rec: DecodedEvent):
        ev = rec.event
        assert isinstance(ev, ExecComplete)
        insn_id = self.rob.get(ev.rob_id)
        if insn_id is None or insn_id in self.terminated:
            return
        self._command(rec.cycle, "S", insn_id, 0, "Cm")

    @handles(RobRetire)
    def on_rob_retire(self, rec: DecodedEvent):
        ev = rec.event
        assert isinstance(ev, RobRetire)
        insn_id = self.rob.pop(ev.rob_id, None)
        if insn_id is None or insn_id in self.terminated:
            return
        self._command(rec.cycle, "R", insn_id, self.next_retire_id, 0)
        self.next_retire_id += 1
        self.terminated.add(insn_id)

    @handles(RobFlush)
    def on_rob_flush(self, rec: DecodedEvent):
        ev = rec.event
        assert isinstance(ev, RobFlush)
        insn_id = self.rob.pop(ev.rob_id, None)
        if insn_id is None or insn_id in self.terminated:
            return
        self._command(rec.cycle, "R", insn_id, 0, 1)
        self.terminated.add(insn_id)

    @handles(FTQCommit)
    def on_commit(self, rec: DecodedEvent):
        ev = rec.event
        assert isinstance(ev, FTQCommit)
        # The commit pointer is the oldest live FTQ entry, so all entries
        # strictly before it are fully retired (each instruction got its own
        # `RobRetire`); they only need to be dropped from the bookkeeping.
        for key in self._entries_before(ev.ftq_ptr):
            del self.blocks[key]

    @handles(FTQRollback)
    def on_rollback(self, rec: DecodedEvent):
        ev = rec.event
        assert isinstance(ev, FTQRollback)
        # `ftq_ptr` is the new allocation pointer: it and everything
        # allocated after it is squashed. Instructions already flushed from
        # the ROB (via `RobFlush`) are skipped; blocks squashed before
        # producing any instructions simply disappear from the log.
        flushed: set[int] = set()
        for key in self._entries_from(ev.ftq_ptr):
            for insn_id in self.blocks.pop(key).instr_ids.values():
                flushed.add(insn_id)
                if insn_id in self.terminated:
                    continue
                self._command(rec.cycle, "R", insn_id, 0, 1)
                self.terminated.add(insn_id)
        self.rob = {rob_id: insn_id for rob_id, insn_id in self.rob.items() if insn_id not in flushed}

    def _entries_before(self, ftq_ptr: int) -> list[int]:
        """Returns the live entries allocated strictly before `ftq_ptr`."""
        keys = list(self.blocks)
        if ftq_ptr not in keys:
            return []
        return keys[: keys.index(ftq_ptr)]

    def _entries_from(self, ftq_ptr: int) -> list[int]:
        """Returns the live entries from `ftq_ptr` through the newest."""
        keys = list(self.blocks)
        if ftq_ptr not in keys:
            return []
        return keys[keys.index(ftq_ptr) :]

    def _write(self):
        self.out.write("Kanata\t0004\n")
        self.timeline.sort(key=lambda command: command[:2])

        current_cycle = self.timeline[0][0] if self.timeline else 0
        self.out.write(f"C=\t{current_cycle}\n")
        for cycle, _, line in self.timeline:
            if cycle != current_cycle:
                self.out.write(f"C\t{cycle - current_cycle}\n")
                current_cycle = cycle
            self.out.write(line + "\n")


def main(argv: Optional[list[str]] = None):
    # Die silently when the output is piped to e.g. `head`.
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)

    parser = argparse.ArgumentParser(description="Convert a captured event log to the Kanata format.")
    parser.add_argument("path", help="The event log file (JSON lines)")
    parser.add_argument("-o", "--output", help="Output file (default: standard output)")
    args = parser.parse_args(argv)

    reader = EventLogReader(args.path)
    if args.output is not None:
        with open(args.output, "w") as out:
            KonataParser(out).run(reader)
    else:
        KonataParser(sys.stdout).run(reader)


if __name__ == "__main__":
    main()
