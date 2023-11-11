from amaranth import *
from typing import TYPE_CHECKING, Generator, Any, TypeAlias, TypeVar, Union
from coreblocks.utils._typing import RecordValueDict, RecordIntDict
from amaranth.hdl.ast import Statement
from amaranth.sim.core import Command

if TYPE_CHECKING:
    from .infrastructure import CoreblockCommand


T = TypeVar("T")
TestGen: TypeAlias = Generator[Union[Command, Value, Statement, "CoreblockCommand", None], Any, T]


def set_inputs(values: RecordValueDict, field: Record) -> "TestGen[None]":
    for name, value in values.items():
        if isinstance(value, dict):
            yield from set_inputs(value, getattr(field, name))
        else:
            yield getattr(field, name).eq(value)


def get_outputs(field: Record) -> "TestGen[RecordIntDict]":
    # return dict of all signal values in a record because amaranth's simulator can't read all
    # values of a Record in a single yield - it can only read Values (Signals)
    result = {}
    for name, _, _ in field.layout:
        val = getattr(field, name)
        if isinstance(val, Signal):
            result[name] = yield val
        else:  # field is a Record
            result[name] = yield from get_outputs(val)
    return result
