from typing import Protocol

from amaranth_types import HasElaborate
from transactron import Method, Provided


class TLBBackingDevice(HasElaborate, Protocol):
    """Protocol for devices that can be used as a backing device for TLBs."""

    request: Provided[Method]
    """Method for requesting a translation.
    Expected layout is `AddressTranslationLayouts.tlb_request`."""

    accept: Provided[Method]
    """Method for accepting a translation response.
    Expected layout is `AddressTranslationLayouts.tlb_accept`."""
