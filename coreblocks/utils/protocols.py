from amaranth import *

from typing import Protocol
from coreblocks.transactions import Method
from coreblocks.params import OpType
from ._typing import HasElaborate


__all__ = ["FuncUnit", "FuncBlock", "Unifier"]


class Unifier(Protocol):
    method: Method

    def __init__(self, targets: list[Method]):
        ...

    def elaborate(self, platform) -> Module:
        ...


class FuncUnit(HasElaborate, Protocol):
    optypes: set[OpType]
    issue: Method
    accept: Method


class FuncBlock(HasElaborate, Protocol):
    optypes: set[OpType]
    insert: Method
    select: Method
    update: Method
    get_result: Method
