from amaranth import *

from coreblocks.transactions import Method
from typing import Optional, TypeVar, Callable, Union, Generic
from ._typing import HasElaborate, SignalBundle
from .protocols import MethodCollection, MethodCollectionElement, MethodCollectionOutput
from abc import abstractmethod, ABC


__all__ = ["ListMethodCollection", "DictMethodCollection"]

T = TypeVar('T')
_T_nested_dict = dict[str, Union[T, '_T_nested_dict']]

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
