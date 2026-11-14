from typing import Protocol

from transactron import Method, Provided

from coreblocks.interface.layouts import AddressTranslationLayouts
from coreblocks.params import GenParams

__all__ = ["TLBBackingDevice", "PureTLBBackingDevice"]


class TLBBackingDevice(Protocol):
    """Protocol for devices that can be used as a backing device for TLBs."""

    request: Provided[Method]
    """Method for requesting a translation.
    Expected layout is `AddressTranslationLayouts.tlb_request`."""

    accept: Provided[Method]
    """Method for accepting a translation response.
    Expected layout is `AddressTranslationLayouts.tlb_accept`."""


class PureTLBBackingDevice(TLBBackingDevice):
    """`TLBBackingDevice` with no behavior of its own."""

    def __init__(self, gen_params: GenParams):
        layout = gen_params.get(AddressTranslationLayouts)
        self.request = Method(i=layout.tlb_request)
        self.accept = Method(o=layout.tlb_accept)
