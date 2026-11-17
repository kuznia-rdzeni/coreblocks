from typing import Protocol

from transactron import Method, Provided
from transactron.lib import PureRequestResponseInterface, RequestResponseInterface
from transactron.utils import SrcLoc, get_src_loc

from coreblocks.interface.layouts import AddressTranslationLayouts
from coreblocks.params import GenParams

__all__ = ["TLBBackingDevice", "PureTLBBackingDevice"]


class TLBBackingDevice(RequestResponseInterface, Protocol):
    """Protocol for devices that can be used as a backing device for TLBs."""

    request: Provided[Method]
    """Method for requesting a translation.
    Expected layout is `AddressTranslationLayouts.tlb_request`."""

    response: Provided[Method]
    """Method for accepting a translation response.
    Expected layout is `AddressTranslationLayouts.tlb_accept`."""


class PureTLBBackingDevice(PureRequestResponseInterface, TLBBackingDevice):
    """`TLBBackingDevice` with no behavior of its own."""

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
        layout = gen_params.get(AddressTranslationLayouts)
        super().__init__(layout.tlb_request, layout.tlb_accept, src_loc=get_src_loc(src_loc))
