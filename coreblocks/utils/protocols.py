from typing import Protocol, runtime_checkable
from coreblocks.transactions import Method
from coreblocks.params.isa import OpType


__all__ = ["FuncUnit", "FuncBlock", "JumpUnit", "LSUUnit"]


class FuncUnit(Protocol):
    optypes: set[OpType]
    issue: Method
    accept: Method


@runtime_checkable
class JumpUnit(Protocol):
    branch_result: Method


@runtime_checkable
class LSUUnit(Protocol):
    commit: Method


class FuncBlock(Protocol):
    optypes: set[OpType]
    insert: Method
    select: Method
    update: Method
    get_result: Method
