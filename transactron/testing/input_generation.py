from amaranth import *
from amaranth.lib.data import StructLayout
import random
from typing import Optional
import hypothesis.strategies as st
from hypothesis.strategies import composite, DrawFn, integers
from transactron.utils import MethodLayout, RecordIntDict

@composite
def generate_shrinkable_list(draw : DrawFn, length : int, generator) -> list:
    """
    Trick based on https://github.com/HypothesisWorks/hypothesis/blob/6867da71beae0e4ed004b54b92ef7c74d0722815/hypothesis-python/src/hypothesis/stateful.py#L143
    """
    hp_data = draw(st.data())
    lst=[]
    if length == 0:
        return lst
    i = 0
    force_val = None
    while True:
        b = hp_data.conjecture_data.draw_boolean(p=2**-16, forced = force_val)
        if b:
            break
        lst.append(draw(generator))
        i += 1
        if i == length:
            force_val = True
    return lst


@composite
def generate_based_on_layout(draw : DrawFn, layout: MethodLayout) -> RecordIntDict:
    if isinstance(layout, StructLayout):
        raise NotImplementedError("StructLayout is not supported in automatic value generation.")
    d = {}
    for name, sublayout in layout:
        if isinstance(sublayout, list):
            elem = draw(generate_based_on_layout(sublayout))
        elif isinstance(sublayout, int):
            elem = draw(integers(min_value=0, max_value=sublayout))
        elif isinstance(sublayout, range):
            elem = draw(integers(min_value=sublayout.start, max_value=sublayout.stop-1))
        elif isinstance(sublayout, Shape):
            if sublayout.signed:
                min_value = -2**(sublayout.width-1)
                max_value = 2**(sublayout.width-1)-1
            else:
                min_value = 0
                max_value = 2**sublayout.width
            elem = draw(integers(min_value = min_value, max_value = max_value))
        else:
            # Currently type[Enum] and ShapeCastable
            raise NotImplementedError("Passed LayoutList with syntax yet unsuported in automatic value generation.")
        d[name] = elem
    return d
