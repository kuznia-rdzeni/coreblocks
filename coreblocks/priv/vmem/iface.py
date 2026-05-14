from typing import Protocol

from transactron import Method, Provided


class TLBBackingDevice(Protocol):
    """Protocol for devices that can be used as a backing device for TLBs."""

    request: Provided[Method]
    """Method for requesting a translation.
    Expected layout is `AddressTranslationLayouts.tlb_request`."""

    accept: Provided[Method]
    """Method for accepting a translation response.
    Expected layout is `AddressTranslationLayouts.tlb_accept`."""
