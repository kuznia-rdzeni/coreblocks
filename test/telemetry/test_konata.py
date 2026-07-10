from io import StringIO
from textwrap import dedent

from transactron.evlog import DecodedEvent, Event, EventSiteSchema

from coreblocks.telemetry import (
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
from coreblocks.telemetry.konata import KonataParser

DUMMY_SITE = EventSiteSchema(source_name="frontend", event_name="dummy", location=("x.py", 1), fields=[], statics={})


def dec(cycle: int, event: Event) -> DecodedEvent:
    return DecodedEvent(cycle=cycle, site=DUMMY_SITE, event=event)


class TestKonataParser:
    def test_convert(self):
        # Two fetch blocks: block 0 produces two instructions which go all
        # the way through the backend and retire, block 1 produces one
        # instruction which is flushed before reaching the ROB.
        records = [
            dec(0, FTQAlloc(ftq_ptr=0, pc=0x100)),
            dec(1, FetchRequest(ftq_ptr=0, pc=0x100)),
            dec(1, FTQAlloc(ftq_ptr=1, pc=0x108)),
            dec(2, FetchRequest(ftq_ptr=1, pc=0x108)),
            dec(3, InstrFetched(ftq_ptr=0, pc=0x100, instr=0x13, ftq_offset=0)),
            dec(3, InstrFetched(ftq_ptr=0, pc=0x104, instr=0x93, ftq_offset=1)),
            dec(4, InstrFetched(ftq_ptr=1, pc=0x108, instr=0x33, ftq_offset=0)),
            dec(5, InstrDecoded(ftq_ptr=0, ftq_offset=0)),
            dec(5, InstrDecoded(ftq_ptr=0, ftq_offset=1)),
            dec(6, SchedulerEnter(ftq_ptr=0, ftq_offset=0)),
            dec(6, SchedulerEnter(ftq_ptr=0, ftq_offset=1)),
            dec(7, RobAllocate(ftq_ptr=0, ftq_offset=0, rob_id=0)),
            dec(7, RobAllocate(ftq_ptr=0, ftq_offset=1, rob_id=1)),
            dec(8, FuIssue(rob_id=0, unit="alu")),
            dec(8, FuIssue(rob_id=1, unit="alu")),
            dec(9, ExecComplete(rob_id=0)),
            dec(9, ExecComplete(rob_id=1)),
            dec(11, RobRetire(rob_id=0)),
            dec(11, RobRetire(rob_id=1)),
            dec(11, FTQCommit(ftq_ptr=0)),
            dec(12, FTQRollback(ftq_ptr=1, cause="backend_redirect")),
        ]

        out = StringIO()
        KonataParser(out).run(records)

        assert out.getvalue() == dedent(
            """\
            Kanata\t0004
            C=\t1
            I\t0\t0\t0
            L\t0\t0\t00000100: nop
            L\t0\t1\tinstr=00000013 ftq_ptr=0 ftq_offset=0
            S\t0\t0\tF
            I\t1\t1\t0
            L\t1\t0\t00000104: mv ra, zero
            L\t1\t1\tinstr=00000093 ftq_ptr=0 ftq_offset=1
            S\t1\t0\tF
            C\t1
            I\t2\t2\t0
            L\t2\t0\t00000108: add zero, zero, zero
            L\t2\t1\tinstr=00000033 ftq_ptr=1 ftq_offset=0
            S\t2\t0\tF
            C\t1
            S\t0\t0\tQ
            S\t1\t0\tQ
            C\t1
            S\t2\t0\tQ
            C\t1
            S\t0\t0\tD
            S\t1\t0\tD
            C\t1
            S\t0\t0\tRn
            S\t1\t0\tRn
            C\t1
            S\t0\t0\tDs
            L\t0\t1\t rob_id=0
            S\t1\t0\tDs
            L\t1\t1\t rob_id=1
            C\t1
            S\t0\t0\tIs
            L\t0\t1\t fu=alu
            S\t1\t0\tIs
            L\t1\t1\t fu=alu
            C\t1
            S\t0\t0\tCm
            S\t1\t0\tCm
            C\t2
            R\t0\t0\t0
            R\t1\t1\t0
            C\t1
            R\t2\t0\t1
            """
        )

    def test_rollback_without_instructions(self):
        # A block squashed before any instruction was fetched leaves no
        # trace in the log.
        records = [
            dec(0, FTQAlloc(ftq_ptr=0, pc=0x100)),
            dec(1, FetchRequest(ftq_ptr=0, pc=0x100)),
            dec(2, FTQRollback(ftq_ptr=0, cause="ifu_writeback")),
        ]

        out = StringIO()
        KonataParser(out).run(records)

        assert out.getvalue() == "Kanata\t0004\nC=\t0\n"

    def test_commit_does_not_terminate_instructions(self):
        # The FTQ commit pointer names the *oldest live* entry: it is emitted
        # per retired instruction and must not terminate anything by itself.
        records = [
            dec(0, FTQAlloc(ftq_ptr=0, pc=0x100)),
            dec(1, InstrFetched(ftq_ptr=0, pc=0x100, instr=0x13, ftq_offset=0)),
            dec(2, FTQAlloc(ftq_ptr=1, pc=0x108)),
            dec(3, RobAllocate(ftq_ptr=0, ftq_offset=0, rob_id=5)),
            dec(4, FTQCommit(ftq_ptr=0)),
            dec(5, FTQCommit(ftq_ptr=1)),
        ]

        out = StringIO()
        KonataParser(out).run(records)

        assert not any(line.startswith("R") for line in out.getvalue().splitlines())

    def test_rob_flush_then_rollback_terminates_once(self):
        # An instruction flushed from the ROB whose FTQ entry is later rolled
        # back gets exactly one terminal record.
        records = [
            dec(0, FTQAlloc(ftq_ptr=0, pc=0x100)),
            dec(1, InstrFetched(ftq_ptr=0, pc=0x100, instr=0x13, ftq_offset=0)),
            dec(2, RobAllocate(ftq_ptr=0, ftq_offset=0, rob_id=3)),
            dec(3, RobFlush(rob_id=3)),
            dec(4, FTQRollback(ftq_ptr=0, cause="backend_redirect")),
        ]

        out = StringIO()
        KonataParser(out).run(records)

        retires = [line for line in out.getvalue().splitlines() if line.startswith("R")]
        assert retires == ["R\t0\t0\t1"]

    def test_unterminated_instructions(self):
        # Instructions still in flight when the log ends stay unterminated.
        records = [
            dec(0, FTQAlloc(ftq_ptr=0, pc=0x100)),
            dec(2, InstrFetched(ftq_ptr=0, pc=0x100, instr=0x13, ftq_offset=0)),
        ]

        out = StringIO()
        KonataParser(out).run(records)

        assert not any(line.startswith("R") for line in out.getvalue().splitlines())

    def test_undisassemblable_instruction_falls_back_to_hex(self):
        records = [
            dec(0, FetchRequest(ftq_ptr=0, pc=0x100)),
            dec(1, InstrFetched(ftq_ptr=0, pc=0x100, instr=0xFFFFFFFF, ftq_offset=0)),
        ]

        out = StringIO()
        KonataParser(out).run(records)

        assert "L\t0\t0\t00000100: ffffffff" in out.getvalue().splitlines()

    def test_decode_of_squashed_instruction_is_ignored(self):
        # A decode event arriving after its FTQ entry was squashed (or for an
        # unknown entry) leaves no trace.
        records = [
            dec(0, FTQAlloc(ftq_ptr=0, pc=0x100)),
            dec(1, InstrFetched(ftq_ptr=0, pc=0x100, instr=0x13, ftq_offset=0)),
            dec(2, FTQRollback(ftq_ptr=0, cause="backend_redirect")),
            dec(3, InstrDecoded(ftq_ptr=0, ftq_offset=0)),
            dec(3, InstrDecoded(ftq_ptr=7, ftq_offset=0)),
        ]

        out = StringIO()
        KonataParser(out).run(records)

        assert not any("\tD" in line for line in out.getvalue().splitlines() if line.startswith("S"))
