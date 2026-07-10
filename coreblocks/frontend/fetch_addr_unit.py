from amaranth import *
from transactron import *
from transactron.utils import make_layout

from coreblocks.params import GenParams
from coreblocks.arch import *
from coreblocks.interface.layouts import (
    CommonLayoutFields,
    FetchLayouts,
)


class FetchAddressUnit(Elaboratable):
    """
    Owns the speculative fetch program counter and arbitrates all frontend redirects.
    It selects the next fetch PC based on reset, backend redirects, IFU redirects, and branch prediction results.
    """

    write: Provided[Method]
    """Supply the next fetch PC (e.g. from a BPU prediction). Requires the current PC to have been consumed."""
    read: Provided[Method]
    """Consume the current fetch PC. Blocks until a valid PC is available."""
    ifu_redirect: Provided[Method]
    """Redirect the fetch PC after a misprediction detected by the IFU."""
    backend_redirect: Provided[Method]
    """Redirect the fetch PC after a misprediction resolved by the backend."""

    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params

        layouts = self.gen_params.get(FetchLayouts)
        fields = self.gen_params.get(CommonLayoutFields)

        self.write = Method(i=make_layout(fields.pc))
        self.read = Method(o=layouts.fetch_request)
        self.ifu_redirect = Method(i=layouts.redirect)
        self.backend_redirect = Method(i=layouts.redirect)

    def elaborate(self, platform):
        m = TModule()

        next_fetch_addr = Signal(self.gen_params.isa.xlen, init=self.gen_params.start_pc)
        next_fetch_addr_v = Signal(init=1)

        next_fetch_addr_fwd = Signal.like(self.read.data_out)

        self.write.schedule_before(self.read)  # to avoid combinational loops

        @def_method(m, self.write, ready=~next_fetch_addr_v)
        def _(pc):
            m.d.av_comb += next_fetch_addr_fwd.eq(pc)
            m.d.sync += next_fetch_addr.eq(pc)
            m.d.sync += next_fetch_addr_v.eq(1)

        with m.If(next_fetch_addr_v):
            m.d.av_comb += next_fetch_addr_fwd.eq(next_fetch_addr)  # write method is not ready

        @def_method(m, self.read, ready=next_fetch_addr_v | self.write.run)
        def _():
            m.d.sync += next_fetch_addr_v.eq(0)
            return next_fetch_addr_fwd

        @def_method(m, self.ifu_redirect)
        def _(pc):
            m.d.sync += next_fetch_addr.eq(pc)
            m.d.sync += next_fetch_addr_v.eq(1)

        @def_method(m, self.backend_redirect)
        def _(pc):
            m.d.sync += next_fetch_addr.eq(pc)
            m.d.sync += next_fetch_addr_v.eq(1)

        return m
