from amaranth import *
import amaranth.lib.data as data
from amaranth.lib.data import Layout, StructLayout, View
from amaranth.sim._pycoro import Command
from typing import TypeVar, Any, Generator, TypeAlias, TYPE_CHECKING, Union
from transactron.utils._typing import RecordIntDict


if TYPE_CHECKING:
    from amaranth.hdl._ast import Statement
    from .infrastructure import CoreblocksCommand


T = TypeVar("T")
TestGen: TypeAlias = Generator[Union[Command, Value, "Statement", "CoreblocksCommand", None], Any, T]
MethodData: TypeAlias = "data.Const[data.StructLayout]"


def data_const_to_dict(c: "data.Const[data.Layout]"):
    ret = {}
    for k, _ in c.shape():
        v = c[k]
        if isinstance(v, data.Const):
            v = data_const_to_dict(v)
        ret[k] = v
    return ret


def get_outputs(field: View) -> TestGen[RecordIntDict]:
    # return dict of all signal values in a record because amaranth's simulator can't read all
    # values of a View in a single yield - it can only read Values (Signals)
    result = {}
    layout = field.shape()
    assert isinstance(layout, StructLayout)
    for name, fld in layout:
        val = field[name]
        if isinstance(fld.shape, Layout):
            result[name] = yield from get_outputs(View(fld.shape, val))
        elif isinstance(val, Value):
            result[name] = yield val
        else:
            raise ValueError
    return result
