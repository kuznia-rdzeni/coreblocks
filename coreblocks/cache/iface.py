from typing import Protocol

from transactron import Method, Provided

from coreblocks.interface.layouts import ICacheLayouts
from coreblocks.params import GenParams

__all__ = ["CacheInterface", "PureCacheInterface", "CacheRefillerInterface", "PureCacheRefillerInterface"]


class CacheInterface(Protocol):
    """Cache Interface."""

    issue_req: Provided[Method]
    """A method that is used to issue a cache lookup request."""

    accept_res: Provided[Method]
    """A method that is used to accept the result of a cache lookup request."""

    flush: Provided[Method]
    """A method that is used to flush the whole cache."""


class PureCacheInterface(CacheInterface):
    """`CacheInterface` with no behavior of its own."""

    def __init__(self, gen_params: GenParams):
        layouts = gen_params.get(ICacheLayouts)
        self.issue_req = Method(i=layouts.issue_req)
        self.accept_res = Method(o=layouts.accept_res)
        self.flush = Method()


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
