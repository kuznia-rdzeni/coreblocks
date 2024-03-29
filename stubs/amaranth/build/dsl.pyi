"""
This type stub file was generated by pyright.
"""

from collections import OrderedDict
from collections.abc import Iterator, Mapping
from typing import Optional

__all__ = ["Pins", "PinsN", "DiffPairs", "DiffPairsN", "Attrs", "Clock", "Subsignal", "Resource", "Connector"]
class Pins:
    def __init__(self, names: str, *, dir: str=..., invert: bool=..., conn: Optional[tuple[str, int|str]]=..., assert_width: Optional[int]=...) -> None:
        ...
    
    def __len__(self) -> int:
        ...
    
    def __iter__(self) -> Iterator[str]:
        ...
    
    def map_names(self, mapping: Mapping[str, str], resource) -> list[str]:
        ...
    
    def __repr__(self) -> str:
        ...
    


def PinsN(*args, **kwargs) -> Pins:
    ...

class DiffPairs:
    def __init__(self, p: str, n: str, *, dir: str=..., invert: bool=..., conn: Optional[tuple[str, int|str]]=..., assert_width: Optional[int]=...) -> None:
        ...
    
    def __len__(self) -> int:
        ...
    
    def __iter__(self) -> Iterator[tuple[str, str]]:
        ...
    
    def __repr__(self) -> str:
        ...
    


def DiffPairsN(*args, **kwargs) -> DiffPairs:
    ...

class Attrs(OrderedDict):
    def __init__(self, **attrs) -> None:
        ...
    
    def __repr__(self) -> str:
        ...
    


class Clock:
    def __init__(self, frequency: float | int) -> None:
        ...
    
    @property
    def period(self) -> float:
        ...
    
    def __repr__(self) -> str:
        ...
    


class Subsignal:
    def __init__(self, name: str, *args: Pins | DiffPairs | Subsignal | Attrs | Clock) -> None:
        ...
    
    def __repr__(self) -> str:
        ...
    


class Resource(Subsignal):
    @classmethod
    def family(cls, name_or_number: str | int, number: Optional[int]=..., *, ios, default_name: str, name_suffix: str=...): # -> Self@Resource:
        ...
    
    def __init__(self, name, number, *args) -> None:
        ...
    
    def __repr__(self) -> str:
        ...
    


class Connector:
    def __init__(self, name: str, number: int, io: str | dict[str, str], *, conn: Optional[tuple[str, int|str]]=...) -> None:
        ...
    
    def __repr__(self) -> str:
        ...
    
    def __len__(self) -> int:
        ...
    
    def __iter__(self) -> Iterator[tuple[str, str]]:
        ...
    


