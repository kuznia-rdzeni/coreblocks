from typing import Protocol
from transactron import Method, Methods, Provided, Required
from coreblocks.func_blocks.fu.common.fu_decoder import DecoderManager
from amaranth_types import HasElaborate


__all__ = ["FuncUnit", "FuncBlock"]


class FuncUnit(HasElaborate, Protocol):
    issue: Provided[Method]
    """Called by RS to send new instruction to the functional unit."""

    push_result: Required[Method]
    """Called by the functional unit to broadcast the result."""


class FuncBlock(HasElaborate, Protocol):
    insert: Method
    select: Method
    update: Methods
    get_result: Method
