from typing import Protocol

from transactron import Method

from amaranth_types import HasElaborate

__all__ = ["ICacheInterface", "DCacheInterface", "CacheRefillerInterface"]


class ICacheInterface(HasElaborate, Protocol):
    """
    Instruction Cache Interface.

    Parameters
    ----------
    issue_req : Method
        A method that is used to issue a cache lookup request.
    accept_res : Method
        A method that is used to accept the result of a cache lookup request.
    flush : Method
        A method that is used to flush the whole cache.
    """

    issue_req: Method
    accept_res: Method
    flush: Method


class DCacheInterface(HasElaborate, Protocol):
    """
    Data Cache Interface.

    Parameters
    ----------
    issue_read : Method
        Issues a cache read request.
    issue_store : Method
        Issues a cache store request.
    accept_read : Method
        Accepts the result of a previously issued read request.
    accept_store : Method
        Accepts the result of a previously issued store request.
    flush : Method
        Flushes the whole cache.
    """

    issue_read: Method
    issue_store: Method
    accept_read: Method
    accept_store: Method
    flush: Method


class CacheRefillerInterface(HasElaborate, Protocol):
    """
    Cache Refiller Interface.

    Parameters
    ----------
    start_refill : Method
        A method that is used to start a refill for a given cache line.
    accept_refill : Method
        A method that is used to accept one fetch block from the requested cache line.
    """

    start_refill: Method
    accept_refill: Method
