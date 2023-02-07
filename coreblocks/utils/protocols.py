from typing import Protocol, runtime_checkable
from coreblocks.transactions import Method
from coreblocks.params import OpType


__all__ = ["FuncUnit", "FuncBlock", "JumpUnit", "LSUUnit", "FuncUnitsHolder"]


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


@runtime_checkable
class FuncUnitsHolder(Protocol):
    func_units: list[FuncUnit]


class FuncBlock(Protocol):
    optypes: set[OpType]
    insert: Method
    select: Method
    update: Method
    get_result: Method
