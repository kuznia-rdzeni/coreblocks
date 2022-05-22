from typing import Union

from amaranth import C, Signal, Record

Wires = Union["C", "Signal", "Record"]
SimpleWires = Union["C", "Signal"]
