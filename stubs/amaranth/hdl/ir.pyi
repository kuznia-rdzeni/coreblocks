"""
This type stub file was generated by pyright.
"""

from abc import ABCMeta, abstractmethod
from .ast import *
from .cd import *
from coreblocks.utils import HasElaborate

__all__ = ["Elaboratable", "DriverConflict", "Fragment", "Instance"]


class Elaboratable():
    @abstractmethod
    def elaborate(self, platform) -> HasElaborate:
        ...


class DriverConflict(UserWarning):
    ...


class Fragment:
    @staticmethod
    def get(obj, platform): # -> Fragment:
        ...
    
    def __init__(self) -> None:
        ...
    
    def add_ports(self, *ports, dir): # -> None:
        ...
    
    def iter_ports(self, dir=...): # -> Generator[Unknown | None, None, None]:
        ...
    
    def add_driver(self, signal, domain=...): # -> None:
        ...
    
    def iter_drivers(self): # -> Generator[tuple[Unknown, Unknown], None, None]:
        ...
    
    def iter_comb(self): # -> Generator[Unknown, None, None]:
        ...
    
    def iter_sync(self): # -> Generator[tuple[Unknown, Unknown], None, None]:
        ...
    
    def iter_signals(self): # -> SignalSet:
        ...
    
    def add_domains(self, *domains): # -> None:
        ...
    
    def iter_domains(self): # -> Generator[Unknown, None, None]:
        ...
    
    def add_statements(self, *stmts): # -> None:
        ...
    
    def add_subfragment(self, subfragment, name=...): # -> None:
        ...
    
    def find_subfragment(self, name_or_index):
        ...
    
    def find_generated(self, *path):
        ...
    
    def elaborate(self, platform): # -> Self@Fragment:
        ...
    
    def prepare(self, ports=..., missing_domain=...):
        ...
    


class Instance(Fragment):
    def __init__(self, type, *args, **kwargs) -> None:
        ...
    


