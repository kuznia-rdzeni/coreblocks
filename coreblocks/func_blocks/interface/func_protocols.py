from typing import Protocol
from transactron import Method, Provided, Required
from amaranth_types import HasElaborate


__all__ = ["FuncUnit", "FuncBlock"]


class FuncUnit(HasElaborate, Protocol):
    issue: Provided[Method]
    push_result: Required[Method]


class FuncBlock(HasElaborate, Protocol):
    insert: Method
    select: Method
    update: Method
    get_result: Method
