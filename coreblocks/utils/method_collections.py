from amaranth import *

from coreblocks.transactions import Method
from typing import Optional, TypeVar, Callable, Union, Generic, Type
from ._typing import HasElaborate, SignalBundle
from .protocols import MethodCollection, MethodCollectionElement, MethodCollectionOutput
from abc import abstractmethod, ABC
from collections.abc import Collection


__all__ = ["ListMethodCollection", "DictMethodCollection"]

T = TypeVar('T')
T2 = TypeVar('T2')
_T_nested_dict = dict[str, Union[T, '_T_nested_dict']]
_T_nested_collection = T | list['_T_nested_collection[T]'] | dict[str, '_T_nested_collection[T]']

class MethodCollectionBase(ABC, MethodCollection):
    @abstractmethod
    def get_all_methods(self) -> MethodCollectionOutput:
        raise NotImplementedError()

    def transform_methods(self, f : Callable[[Method], T]) -> _T_nested_dict[T]:
        output = {}

        methods = self.get_all_methods()
        for k, elem in methods.items():
            if isinstance(elem, Method):
                output[k] = f(elem)
            else:
                output[k] = self.transform_methods(f)
        return output

    def debug_signals(self) -> SignalBundle:
        return self.transform_methods(lambda m: m.debug_signals())

class ListMethodCollection(MethodCollectionBase):

    def __init__(self, elements : list[MethodCollectionElement], name_prefix : str = ""):
        self.elements = elements
        self.name_prefix = name_prefix

    def get_all_methods(self) -> MethodCollectionOutput:
        result = {}
        for i, elem in enumerate(self.elements):
            if isinstance(elem, Method):
                result[self.name_prefix+str(i)] = elem
            else:
                result[self.name_prefix+str(i)] = elem.get_all_methods()
        return result

class DictMethodCollection(MethodCollectionBase):

    def __init__(self, elements : dict[str,MethodCollectionElement]):
        self.elements = elements

    def get_all_methods(self) -> MethodCollectionOutput:
        result = {}
        for key, elem in self.elements.items():
            if isinstance(elem, Method):
                result[key] = elem
            else:
                result[key] = elem.get_all_methods()
        return result

# Second proposition:

def transform_collection_deep(container : _T_nested_collection[T], f : Callable[[str, T], T2],*, list_prefix : str="") -> _T_nested_collection[T2]:
    if isinstance(container, list):
        return [transform_collection_deep(elem, lambda n, x: f(list_prefix+str(i)+n, x), list_prefix="") for i,elem in enumerate(container)]
    elif isinstance(container, dict):
        return dict([ (name, transform_collection_deep(elem, lambda n, x: f(name+n, x), list_prefix=list_prefix)) for name, elem in container.items() ])
    else:
        return f("", container)

def transform_type_collection_deep(type : Type, container : _T_nested_collection[T], f : Callable[[str, Method], T2],*, list_prefix : str="") -> _T_nested_collection[Optional[T2]]:
    def f_type(name, x):
        if isinstance(x, type):
            return f(name, x)
        return None
    return transform_collection_deep(container, f_type, list_prefix=list_prefix)


# Usage example:
#
# Original code:
# if isinstance(attr, list):
#     for i, elem in enumerate(attr):
#         if isinstance(elem, Method):
#             self._io[name + str(i)] = TestbenchIO(AdapterTrans(elem))
#             m.submodules[name + str(i)] = self._io[name + str(i)]
#
# New code:
# if isinstance(attr, Collection):
#   self._io[name] = transform_type_collection_deep(Method, attr, lambda _, elem:TestbenchIO(AdapterTrans(elem)))
#   transform_type_collection_deep(Method, self._io[name], lambda n, elem: m.submodules[n] = elem)
