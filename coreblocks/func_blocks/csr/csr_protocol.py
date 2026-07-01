from typing import Protocol

from transactron.core import Method, Provided
from transactron.utils import SrcLoc

__all__ = [
    "RegisteredCSRProtocol",
]


class RegisteredCSRProtocol(Protocol):
    """Protocol required to be included as a public CSR via `CSRListKey`"""

    _fu_read: Provided[Method]
    _fu_write: Provided[Method]
    _fu_access_valid: Provided[Method]

    src_loc: SrcLoc
