from amaranth import *

from collections.abc import Mapping, Iterable
from typing import Protocol, TypeAlias, Union
from coreblocks.transactions import Method
from coreblocks.params import OpType
from ._typing import HasElaborate, SignalBundle


__all__ = ["FuncUnit", "FuncBlock", "Unifier", "MethodCollection"]

MethodCollectionElement : TypeAlias = Union[Method, "MethodCollection"]
MethodCollectionOutput = Mapping[str, Union[Method, "MethodCollectionOutput"]]

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

class MethodCollection(Protocol):

    def get_all_methods(self) -> MethodCollectionOutput:  
        ...

    def debug_signals(self) -> SignalBundle:
        ...
