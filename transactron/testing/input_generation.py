from amaranth import *
from amaranth.lib.data import StructLayout
from typing import TypeVar
import hypothesis.strategies as st
from hypothesis.strategies import composite, DrawFn, integers, SearchStrategy
from transactron.utils import MethodLayout, RecordIntDict


class OpNOP:
    def __repr__(self):
        return "OpNOP()"


T = TypeVar("T")


@composite
def generate_shrinkable_list(draw: DrawFn, length: int, generator: SearchStrategy[T]) -> list[T]:
    """
    Trick based on https://github.com/HypothesisWorks/hypothesis/blob/
    6867da71beae0e4ed004b54b92ef7c74d0722815/hypothesis-python/src/hypothesis/stateful.py#L143
    """
    hp_data = draw(st.data())
    lst = []
    if length == 0:
        return lst
    i = 0
    force_val = None
    while True:
        b = hp_data.conjecture_data.draw_boolean(p=2**-16, forced=force_val)
        if b:
            break
        lst.append(draw(generator))
        i += 1
        if i == length:
            force_val = True
    return lst


@composite
def generate_based_on_layout(draw: DrawFn, layout: MethodLayout) -> RecordIntDict:
    if isinstance(layout, StructLayout):
        raise NotImplementedError("StructLayout is not supported in automatic value generation.")
    d = {}
    for name, sublayout in layout:
        if isinstance(sublayout, list):
            elem = draw(generate_based_on_layout(sublayout))
        elif isinstance(sublayout, int):
            elem = draw(integers(min_value=0, max_value=sublayout))
        elif isinstance(sublayout, range):
            elem = draw(integers(min_value=sublayout.start, max_value=sublayout.stop - 1))
        elif isinstance(sublayout, Shape):
            if sublayout.signed:
                min_value = -(2 ** (sublayout.width - 1))
                max_value = 2 ** (sublayout.width - 1) - 1
            else:
                min_value = 0
                max_value = 2**sublayout.width
            elem = draw(integers(min_value=min_value, max_value=max_value))
        else:
            # Currently type[Enum] and ShapeCastable
            raise NotImplementedError("Passed LayoutList with syntax yet unsuported in automatic value generation.")
        d[name] = elem
    return d


def insert_nops(draw: DrawFn, max_nops: int, lst: list):
    nops_nr = draw(integers(min_value=0, max_value=max_nops))
    for i in range(nops_nr):
        lst.append(OpNOP())
    return lst


@composite
def generate_nops_in_list(draw: DrawFn, max_nops: int, generate_list: SearchStrategy[list[T]]) -> list[T | OpNOP]:
    lst = draw(generate_list)
    out_lst = []
    out_lst = insert_nops(draw, max_nops, out_lst)
    for i in lst:
        out_lst.append(i)
        out_lst = insert_nops(draw, max_nops, out_lst)
    return out_lst


@composite
def generate_method_input(draw: DrawFn, args: list[tuple[str, MethodLayout]]) -> dict[str, RecordIntDict]:
    out = []
    for name, layout in args:
        out.append((name, draw(generate_based_on_layout(layout))))
    return dict(out)


@composite
def generate_process_input(
    draw: DrawFn, elem_count: int, max_nops: int, layouts: list[tuple[str, MethodLayout]]
) -> list[dict[str, RecordIntDict] | OpNOP]:
    return draw(generate_nops_in_list(max_nops, generate_shrinkable_list(elem_count, generate_method_input(layouts))))
