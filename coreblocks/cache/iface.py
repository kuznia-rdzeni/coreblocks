from typing import Protocol

from transactron import Method, Provided
from transactron.lib import PureRequestResponseInterface, RequestResponseInterface
from transactron.utils import SrcLoc, get_src_loc

from coreblocks.interface.layouts import ICacheLayouts
from coreblocks.params import GenParams

__all__ = ["CacheInterface", "PureCacheInterface", "CacheRefillerInterface", "PureCacheRefillerInterface"]


class CacheInterface(RequestResponseInterface, Protocol):
    """Cache Interface."""

    request: Provided[Method]
    """A method that is used to issue a cache lookup request."""

    response: Provided[Method]
    """A method that is used to accept the result of a cache lookup request."""

    flush: Provided[Method]
    """A method that is used to flush the whole cache."""


class PureCacheInterface(PureRequestResponseInterface, CacheInterface):
    """`CacheInterface` with no behavior of its own."""

    def __init__(self, gen_params: GenParams, *, src_loc: int | SrcLoc = 0):
        """
        Parameters
        ----------
        gen_params: GenParams
            Core generation parameters.
        src_loc: int | SrcLoc
            How many stack frames deep the source location is taken from.
            Alternatively, the source location to use instead of the default.
        """
        src_loc = get_src_loc(src_loc)
        layouts = gen_params.get(ICacheLayouts)
        super().__init__(layouts.issue_req, layouts.accept_res, src_loc=src_loc)
        self.flush = Method(src_loc=src_loc)


class CacheRefillerInterface(Protocol):
    """Cache Refiller Interface."""

    start_refill: Provided[Method]
    """A method that is used to start a refill for a given cache line."""

    accept_refill: Provided[Method]
    """A method that is used to accept one fetch block from the requested cache line."""


class PureCacheRefillerInterface(CacheRefillerInterface):
    """`CacheRefillerInterface` with no behavior of its own."""

    def __init__(self, gen_params: GenParams):
        layouts = gen_params.get(ICacheLayouts)
        self.start_refill = Method(i=layouts.start_refill)
        self.accept_refill = Method(o=layouts.accept_refill)
