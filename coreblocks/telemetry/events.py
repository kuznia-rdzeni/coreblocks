import re

from transactron.evlog import Event, Static, event

__all__ = [
    "FTQAlloc",
    "FetchRequest",
    "InstrFetched",
    "InstrDecoded",
    "FTQRollback",
    "FTQCommit",
    "SchedulerEnter",
    "RobAllocate",
    "RobRetire",
    "RobFlush",
    "FuIssue",
    "ExecComplete",
    "func_unit_kind",
]


def func_unit_kind(func_unit) -> str:
    """A short name for a functional unit instance, derived from its class
    name: ``JumpBranchFuncUnit`` -> ``jump_branch``."""
    name = type(func_unit).__name__.removesuffix("FuncUnit").removesuffix("Unit")
    # insert '_' at camelCase word boundaries, keeping acronym runs (e.g. LSU) together
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", "_", name).lower()


@event("frontend.ftq_alloc")
class FTQAlloc(Event):
    """An FTQ entry was allocated for the fetch block at `pc`."""

    ftq_ptr: int
    pc: int


@event("frontend.fetch_request")
class FetchRequest(Event):
    """The FTQ issued a request to the instruction fetch unit for the fetch
    block owned by the FTQ entry."""

    ftq_ptr: int
    pc: int


@event("frontend.instr_fetched")
class InstrFetched(Event):
    """The fetch unit produced a single instruction and sent it towards
    the decode stage. `ftq_offset` is the instruction's slot index within
    its fetch block."""

    ftq_ptr: int
    pc: int
    instr: int
    ftq_offset: Static[int]


@event("frontend.instr_decoded")
class InstrDecoded(Event):
    """An instruction landed in the decode stage. The instruction is
    identified by its FTQ entry and the slot index within it."""

    ftq_ptr: int
    ftq_offset: int


@event("frontend.ftq_rollback")
class FTQRollback(Event):
    """FTQ allocation was rolled back: `ftq_ptr` is the new allocation
    pointer, so all entries from `ftq_ptr` onward are squashed."""

    ftq_ptr: int
    cause: Static[str]


@event("frontend.ftq_commit")
class FTQCommit(Event):
    """The FTQ commit pointer advanced to `ftq_ptr`: this entry is now the
    oldest live one, and all entries strictly before it are fully retired
    and freed. Emitted per retired instruction, so an entry with several
    instructions produces multiple commits of the same pointer."""

    ftq_ptr: int


@event("backend.scheduler_enter")
class SchedulerEnter(Event):
    """The instruction entered the scheduler."""

    ftq_ptr: int
    ftq_offset: int


@event("backend.rob_allocate")
class RobAllocate(Event):
    """A ROB entry was allocated for the instruction; from this point on
    the instruction is identified by its `rob_id`."""

    ftq_ptr: int
    ftq_offset: int
    rob_id: int


@event("backend.rob_retire")
class RobRetire(Event):
    """The instruction retired."""

    rob_id: int


@event("backend.rob_flush")
class RobFlush(Event):
    """The instruction was squashed from the ROB without retiring."""

    rob_id: int


@event("backend.fu_issue")
class FuIssue(Event):
    """The instruction was issued from a reservation station to a
    functional unit."""

    rob_id: int
    unit: Static[str]


@event("backend.exec_complete")
class ExecComplete(Event):
    """The instruction finished executing: its result was announced and the
    ROB entry was marked done."""

    rob_id: int
