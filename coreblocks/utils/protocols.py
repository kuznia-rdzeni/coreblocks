from typing import Protocol
from coreblocks.transactions import Method
from coreblocks.params import OpType


__all__ = ["FuncUnit", "FuncBlock"]


class FuncUnit(Protocol):
    optypes: set[OpType]
    issue: Method
    accept: Method


class FuncBlock(Protocol):
    optypes: set[OpType]
    insert: Method
    select: Method
    update: Method
    get_result: Method
