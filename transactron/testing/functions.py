from amaranth import *
from amaranth.lib.data import Layout, StructLayout, ArrayLayout, View
from amaranth.sim.core import Command
from typing import TypeVar, Any, Generator, TypeAlias, TYPE_CHECKING, Union
from transactron.utils._typing import RecordIntDict


if TYPE_CHECKING:
    from amaranth.hdl._ast import Statement
    from .infrastructure import CoreblocksCommand


T = TypeVar("T")
TestGen: TypeAlias = Generator[Union[Command, Value, "Statement", "CoreblocksCommand", None], Any, T]


def get_outputs(field: View) -> TestGen[RecordIntDict]:
    # return dict of all signal values in a record because amaranth's simulator can't read all
    # values of a View in a single yield - it can only read Values (Signals)
    result = {}
    layout = field.shape()
    assert isinstance(layout, StructLayout) or isinstance(layout, ArrayLayout)
    for name, fld in layout:
        val = field[name]
        if isinstance(fld.shape, Layout):
            result[name] = yield from get_outputs(View(fld.shape, val))
        elif isinstance(val, Value):
            result[name] = yield val
        else:
            raise ValueError
    return result
