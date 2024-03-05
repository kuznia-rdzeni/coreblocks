"""
This type stub file was generated by pyright.
"""

from .. import *
from ..asserts import *
from transactron.utils import HasElaborate

"""First-in first-out queues."""
__all__ = ["FIFOInterface", "SyncFIFO", "SyncFIFOBuffered", "AsyncFIFO", "AsyncFIFOBuffered"]
class FIFOInterface:
    width: int
    depth: int
    w_data: Signal
    w_rdy: Signal
    w_en: Signal
    w_level: Signal
    r_data: Signal
    r_rdy: Signal
    r_en: Signal
    r_level: Signal
    def __init__(self, *, width: int, depth: int) -> None:
        ...
    


class SyncFIFO(Elaboratable, FIFOInterface):
    def __init__(self, *, width: int, depth: int) -> None:
        ...
    
    def elaborate(self, platform) -> HasElaborate:
        ...
    


class SyncFIFOBuffered(Elaboratable, FIFOInterface):
    def __init__(self, *, width: int, depth: int) -> None:
        ...
    
    def elaborate(self, platform) -> HasElaborate:
        ...
    


class AsyncFIFO(Elaboratable, FIFOInterface):
    def __init__(self, *, width: int, depth: int, r_domain: str = ..., w_domain: str = ..., exact_depth: bool = ...) -> None:
        ...
    
    def elaborate(self, platform) -> HasElaborate:
        ...
    


class AsyncFIFOBuffered(Elaboratable, FIFOInterface):
    def __init__(self, *, width: int, depth: int, r_domain: str = ..., w_domain: str = ..., exact_depth: bool = ...) -> None:
        ...
    
    def elaborate(self, platform) -> HasElaborate:
        ...
    


