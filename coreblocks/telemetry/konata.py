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
from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Optional, TextIO
import capstone

from transactron.evlog import DecodedEvent, EventConsumer, EventLogReader, handles

from .events import *


__all__ = ["KonataParser"]


@dataclass
class _Block:
    """A fetch block owned by a live FTQ entry, buffered until its concrete
    instructions are known."""

    pc: int
    fetch_cycle: Optional[int] = None
    instr_ids: dict[int, int] = field(default_factory=dict)
    """Kanata instruction ids of the block's instructions still in the
    frontend, keyed by the FTQ offset."""


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
    - "IX" (issue) from being issued to a functional unit, up to and
      including the cycle in which the result is announced: Konata takes
      the last cycle of a stage named with "X" as the cycle in which the
      result is produced, and draws dependency arrows from it,
    - "Cm" (complete) from the cycle after the announcement, while the
      instruction waits for retirement.

    The instruction terminates by retiring (`RobRetire`) or being squashed.
    Instructions still in flight when the event log ends are left unterminated.
    A stage starting in the cycle of termination is omitted: the instruction
    never really spent time in it (e.g. it retired right after completing,
    or it was flushed while being written into a frontend buffer), and
    Konata would draw it as a bare label.

    A frontend flush (`FTQRollback`) takes effect at the end of its cycle,
    and squashes only the instructions which have not yet entered the
    scheduler. The scheduler is never flushed, so wrong-path instructions
    which left the frontend proceed to the ROB and are squashed from there
    (`RobFlush`).
    """

    def __init__(self, out: TextIO):
        self.out = out
        # Live FTQ entries, keyed by the raw FTQ pointer (with the parity
        # bit, which makes keys unique among live entries); insertion order
        # is allocation order.
        self.blocks: dict[int, _Block] = {}
        # Kanata instruction ids of instructions between entering the
        # scheduler and ROB allocation, keyed by (FTQ pointer, FTQ offset).
        # A key can repeat when a squashed FTQ entry is reallocated while
        # its wrong-path instructions are still in the scheduler; the
        # scheduler is in-order, so the oldest one is allocated first.
        self.scheduler: defaultdict[tuple[int, int], deque[int]] = defaultdict(deque)
        # Kanata instruction ids of live ROB entries, keyed by the ROB id.
        self.rob: dict[int, int] = {}
        # Physical register ids associated with Kanata instruction ids.
        self.rp_dst: dict[int, int] = {}
        # Kanata instuction ids keyed by target physical register ids.
        self.by_rp_dst: dict[int, int] = {}
        # Kanata instruction ids with a terminal (retire/flush) record.
        self.terminated: set[int] = set()
        # Timeline positions of the last stages of live instructions, keyed
        # by Kanata instruction ids.
        self.last_stage: dict[int, int] = {}
        # Timeline positions of the stages omitted on termination.
        self.omitted: set[int] = set()
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
        # A frontend flush takes effect at the end of its cycle, so rollbacks
        # are handled after the other events of the cycle (the base class
        # sorts by cycle, which keeps this order).
        super().run(sorted(records, key=lambda rec: isinstance(rec.event, FTQRollback)))
        self._write()

    def _command(self, cycle: int, *columns) -> None:
        self.timeline.append((cycle, len(self.timeline), "\t".join(str(col) for col in columns)))

    def _stage(self, cycle: int, insn_id: int, name: str) -> None:
        # Stages are not always logged in order, e.g. a completion can be
        # logged before the issue in the same cycle.
        last = self.last_stage.get(insn_id)
        if last is None or cycle >= self.timeline[last][0]:
            self.last_stage[insn_id] = len(self.timeline)
        self._command(cycle, "S", insn_id, 0, name)

    def _terminate(self, cycle: int, insn_id: int, retire_id: int, flush: int) -> None:
        stage = self.last_stage.pop(insn_id, None)
        if stage is not None and self.timeline[stage][0] >= cycle:
            self.omitted.add(stage)
        self._command(cycle, "R", insn_id, retire_id, flush)
        self.terminated.add(insn_id)
        self._forget_dst(insn_id)

    def _forget_dst(self, insn_id: int) -> None:
        """Drops the destination register mapping of a terminated instruction,
        unless the register was already reallocated to a younger one."""
        rp_dst = self.rp_dst.pop(insn_id, None)
        if rp_dst is not None and self.by_rp_dst.get(rp_dst) == insn_id:
            del self.by_rp_dst[rp_dst]

    @handles(FTQAlloc)
    def on_alloc(self, rec: DecodedEvent[FTQAlloc]):
        ev = rec.event
        # The allocation itself is not visualized (the FTQ entry's lifetime
        # differs from the instructions'), but the entry must be tracked so
        # that commits and rollbacks cover it.
        self.blocks[ev.ftq_ptr] = _Block(pc=ev.pc)

    @handles(FetchRequest)
    def on_fetch_request(self, rec: DecodedEvent[FetchRequest]):
        ev = rec.event
        block = self.blocks.setdefault(ev.ftq_ptr, _Block(pc=ev.pc))
        block.fetch_cycle = rec.cycle

    @handles(InstrFetched)
    def on_instr_fetched(self, rec: DecodedEvent[InstrFetched]):
        ev = rec.event
        block = self.blocks.setdefault(ev.ftq_ptr, _Block(pc=ev.pc))

        insn_id = self.next_id
        self.next_id += 1
        block.instr_ids[ev.ftq_offset] = insn_id

        start = block.fetch_cycle if block.fetch_cycle is not None else rec.cycle

        self._command(start, "I", insn_id, insn_id, 0)
        self._command(start, "L", insn_id, 0, f"{ev.pc:08x}: {self._format_instr(ev.pc, ev.instr)}")
        self._command(start, "L", insn_id, 1, f"instr={ev.instr:08x} ftq_ptr={ev.ftq_ptr} ftq_offset={ev.ftq_offset}")
        self._stage(start, insn_id, "F")
        self._stage(rec.cycle, insn_id, "Q")

    @handles(InstrDecoded)
    def on_instr_decoded(self, rec: DecodedEvent[InstrDecoded]):
        ev = rec.event
        block = self.blocks.get(ev.ftq_ptr)
        if block is None or ev.ftq_offset not in block.instr_ids:
            return
        self._stage(rec.cycle, block.instr_ids[ev.ftq_offset], "D")

    @handles(SchedulerEnter)
    def on_scheduler_enter(self, rec: DecodedEvent[SchedulerEnter]):
        ev = rec.event
        block = self.blocks.get(ev.ftq_ptr)
        if block is None or ev.ftq_offset not in block.instr_ids:
            return
        insn_id = block.instr_ids.pop(ev.ftq_offset)
        self.scheduler[(ev.ftq_ptr, ev.ftq_offset)].append(insn_id)
        self._stage(rec.cycle, insn_id, "Rn")

    @handles(RobAllocate)
    def on_rob_allocate(self, rec: DecodedEvent[RobAllocate]):
        ev = rec.event
        pending = self.scheduler.get((ev.ftq_ptr, ev.ftq_offset))
        if not pending:
            return
        insn_id = pending.popleft()
        self.rob[ev.rob_id] = insn_id
        if ev.rp_dst:
            self.rp_dst[insn_id] = ev.rp_dst
            self.by_rp_dst[ev.rp_dst] = insn_id
        self._stage(rec.cycle, insn_id, "Ds")
        self._command(rec.cycle, "L", insn_id, 1, f" rob_id={ev.rob_id}")

    @handles(FuIssue)
    def on_fu_issue(self, rec: DecodedEvent[FuIssue]):
        ev = rec.event
        insn_id = self.rob.get(ev.rob_id)
        if insn_id is None or insn_id in self.terminated:
            return
        self._stage(rec.cycle, insn_id, "IX")
        self._command(rec.cycle, "L", insn_id, 1, f" fu={ev.unit}")

    @handles(ExecComplete)
    def on_exec_complete(self, rec: DecodedEvent[ExecComplete]):
        ev = rec.event
        insn_id = self.rob.get(ev.rob_id)
        if insn_id is None or insn_id in self.terminated:
            return
        self._stage(rec.cycle + 1, insn_id, "Cm")

    @handles(OperandWakeup)
    def on_update(self, rec: DecodedEvent[OperandWakeup]):
        ev = rec.event
        insn_id = self.rob.get(ev.rob_id)
        producer_id = self.by_rp_dst.get(ev.reg_id)
        if insn_id is None or producer_id is None or insn_id in self.terminated:
            return
        self._command(rec.cycle, "W", insn_id, producer_id, 0)

    @handles(RobRetire)
    def on_rob_retire(self, rec: DecodedEvent[RobRetire]):
        ev = rec.event
        insn_id = self.rob.pop(ev.rob_id, None)
        if insn_id is None or insn_id in self.terminated:
            return
        self._terminate(rec.cycle, insn_id, self.next_retire_id, 0)
        self.next_retire_id += 1

    @handles(RobFlush)
    def on_rob_flush(self, rec: DecodedEvent[RobFlush]):
        ev = rec.event
        insn_id = self.rob.pop(ev.rob_id, None)
        if insn_id is None or insn_id in self.terminated:
            return
        self._terminate(rec.cycle, insn_id, 0, 1)

    @handles(FTQCommit)
    def on_commit(self, rec: DecodedEvent[FTQCommit]):
        ev = rec.event
        # The commit pointer is the oldest live FTQ entry, so all entries
        # strictly before it are fully retired (each instruction got its own
        # `RobRetire`); they only need to be dropped from the bookkeeping.
        for key in self._entries_before(ev.ftq_ptr):
            del self.blocks[key]

    @handles(FTQRollback)
    def on_rollback(self, rec: DecodedEvent[FTQRollback]):
        ev = rec.event
        # `ftq_ptr` is the new allocation pointer: it and everything
        # allocated after it is squashed. Only the instructions still in the
        # frontend are flushed; blocks squashed before producing any
        # instructions simply disappear from the log.
        for key in self._entries_from(ev.ftq_ptr):
            for insn_id in self.blocks.pop(key).instr_ids.values():
                self._terminate(rec.cycle, insn_id, 0, 1)

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
        self.timeline = [command for command in self.timeline if command[1] not in self.omitted]
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
