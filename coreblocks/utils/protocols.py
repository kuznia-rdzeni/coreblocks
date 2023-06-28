from typing import Protocol
from coreblocks.transactions import Method
from ._typing import HasElaborate, LayoutLike


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

class RSLayoutProtocol(Protocol):
    data_layout : LayoutLike
    select_out : LayoutLike
    insert_in : LayoutLike
    update_in : LayoutLike
    take_in : LayoutLike
    take_out : LayoutLike
    get_ready_list_out : LayoutLike
