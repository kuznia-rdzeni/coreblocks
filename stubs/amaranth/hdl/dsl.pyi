"""
This type stub file was generated by pyright.
"""

from contextlib import _GeneratorContextManager, contextmanager
from typing import Callable, ContextManager, Iterator, NoReturn, OrderedDict, ParamSpec, TypeVar
from typing_extensions import Self
from .ast import *
from .ir import *
from .cd import *
from .xfrm import *

__all__ = ["SyntaxError", "SyntaxWarning", "Module"]


_P = ParamSpec("_P")
_T = TypeVar("_T")


class SyntaxError(Exception):
    ...


class SyntaxWarning(Warning):
    ...


class _ModuleBuilderProxy:
    def __init__(self, builder, depth) -> None:
        ...
    


class _ModuleBuilderDomain(_ModuleBuilderProxy):
    def __init__(self, builder, depth, domain) -> None:
        ...
    
    def __iadd__(self, assigns: StatementLike) -> Self@_ModuleBuilderDomain:
        ...
    


class _ModuleBuilderDomains(_ModuleBuilderProxy):
    def __getattr__(self, name: str) -> _ModuleBuilderDomain:
        ...
    
    def __getitem__(self, name: str) -> _ModuleBuilderDomain:
        ...
    
    def __setattr__(self, name: str, value) -> None:
        ...
    
    def __setitem__(self, name: str, value) -> None:
        ...
    


class _ModuleBuilderRoot:
    d: _ModuleBuilderDomains

    def __init__(self, builder, depth) -> None:
        ...
    
    def __getattr__(self, name):
        ...
    


class _ModuleBuilderSubmodules:
    def __init__(self, builder) -> None:
        ...
    
    def __iadd__(self, modules): # -> Self@_ModuleBuilderSubmodules:
        ...
    
    def __setattr__(self, name, submodule): # -> None:
        ...
    
    def __setitem__(self, name, value): # -> None:
        ...
    
    def __getattr__(self, name):
        ...
    
    def __getitem__(self, name):
        ...
    


class _ModuleBuilderDomainSet:
    def __init__(self, builder) -> None:
        ...
    
    def __iadd__(self, domains): # -> Self@_ModuleBuilderDomainSet:
        ...
    
    def __setattr__(self, name, domain): # -> None:
        ...
    


class _GuardedContextManager(_GeneratorContextManager[_T]):
    def __init__(self, keyword, func, args, kwds) -> None:
        ...
    
    def __bool__(self) -> NoReturn:
        ...
    

def _guardedcontextmanager(keyword: str) -> Callable[[Callable[_P, Iterator[_T]]], Callable[_P, _GuardedContextManager[_T]]]:
    ...


class FSM:
    def __init__(self, state: Signal, encoding: OrderedDict[str, int], decoding: OrderedDict[int, str]) -> None:
        ...
    
    def ongoing(self, name: str) -> Value:
        ...
    


class Module(_ModuleBuilderRoot, Elaboratable):
    @classmethod
    def __init_subclass__(cls):
        ...
    
    def __init__(self) -> None:
        ...
    
    @_guardedcontextmanager("If")
    def If(self, cond: ValueLike) -> Iterator[None]:
        ...
    
    @_guardedcontextmanager("Elif")
    def Elif(self, cond: ValueLike) -> Iterator[None]:
        ...
    
    @_guardedcontextmanager("Else")
    def Else(self) -> Iterator[None]:
        ...
    
    @contextmanager
    def Switch(self, test: ValueLike) -> Iterator[None]:
        ...
    
    @contextmanager
    def Case(self, *patterns: SwitchKey) -> Iterator[None]:
        ...
    
    def Default(self) -> ContextManager[None]:
        ...
    
    @contextmanager
    def FSM(self, reset: str = ..., domain: str = ..., name: str = ...) -> Iterator[FSM]:
        ...
    
    @contextmanager
    def State(self, name: str) -> Iterator[None]:
        ...
    
    @property
    def next(self) -> NoReturn:
        ...
    
    @next.setter
    def next(self, name: str) -> None:
        ...
    
    def elaborate(self, platform) -> Fragment:
        ...
    


