from typing import Protocol
from coreblocks.transactions import Method
from ._typing import HasElaborate


__all__ = ["FuncUnit", "FuncBlock", "Unifier", "RoutingBlock"]


class Unifier(HasElaborate, Protocol):
    method: Method

    def __init__(self, targets: list[Method]):
        ...


class FuncUnit(HasElaborate, Protocol):
    issue: Method
    accept: Method


class FuncBlock(HasElaborate, Protocol):
    insert: Method
    select: Method
    update: Method
    get_result: Method


class RoutingBlock(HasElaborate, Protocol):
    send: list[Method]
    receive: list[Method]
