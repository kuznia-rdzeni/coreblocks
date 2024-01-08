from typing import Protocol
from transactron import Method
from transactron.utils._typing import HasElaborate


__all__ = ["FuncUnit", "FuncBlock"]


class FuncUnit(HasElaborate, Protocol):
    issue: Method
    accept: Method


class FuncBlock(HasElaborate, Protocol):
    insert: Method
    select: Method
    update: Method
    get_result: Method
