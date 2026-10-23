from amaranth import *
from transactron import *
from transactron.utils import logging, make_layout

from coreblocks.params import GenParams
from coreblocks.arch import *
from coreblocks.interface.layouts import (
    CommonLayoutFields,
    FetchLayouts,
)

log = logging.HardwareLogger("frontend.fau")


class FetchAddressUnit(Elaboratable):
    """
    Owns the speculative fetch program counter and arbitrates all frontend redirects.
    It selects the next fetch PC based on reset, backend redirects, IFU redirects, and branch prediction results.
    """

    write: Provided[Method]
    """Supply the next fetch PC, replacing any stored prediction. Forwarded to a `read` in the same cycle."""
    bpu_redirect: Provided[Method]
    """
    Replace the next fetch PC with a BPU correction.
    """
    read: Provided[Method]
    """Consume the current fetch PC. Blocks until a valid PC is available."""
    ifu_redirect: Provided[Method]
    """
    Redirect the fetch PC after a misprediction detected by the IFU, or - when `pc_valid` is
    low - invalidate it, because the IFU doesn't know where to fetch next.
    """
    backend_redirect: Provided[Method]
    """Redirect the fetch PC after a misprediction resolved by the backend."""

    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params

        layouts = self.gen_params.get(FetchLayouts)
        fields = self.gen_params.get(CommonLayoutFields)

        self.write = Method(i=make_layout(fields.pc))
        self.bpu_redirect = Method(i=make_layout(fields.pc))
        self.read = Method(o=layouts.fetch_request)
        self.ifu_redirect = Method(i=layouts.ifu_redirect)
        self.backend_redirect = Method(i=layouts.redirect)

    def elaborate(self, platform):
        m = TModule()

        next_fetch_addr = Signal(self.gen_params.isa.xlen, init=self.gen_params.start_pc)
        next_fetch_addr_v = Signal(init=1)

        next_fetch_addr_fwd = Signal.like(self.read.data_out)

        self.write.schedule_before(self.read)  # to avoid combinational loops

        # Always ready, so it never stalls the BPU. The slot is still always empty here: a
        # redirect refilling it flushes the prediction, and a correction blocks allocation.
        @def_method(m, self.write)
        def _(pc):
            log.assertion(m, ~next_fetch_addr_v, "BPU target would overwrite an unconsumed fetch PC")
            m.d.sync += next_fetch_addr.eq(pc)

        m.d.av_comb += next_fetch_addr_fwd.eq(Mux(self.write.run, self.write.data_in.pc, next_fetch_addr))

        @def_method(m, self.read, ready=next_fetch_addr_v | self.write.run)
        def _():
            return next_fetch_addr_fwd

        m.d.sync += next_fetch_addr_v.eq((next_fetch_addr_v | self.write.run) & ~self.read.run)

        @def_method(m, self.bpu_redirect)
        def _(pc):
            log.assertion(m, ~self.read.run, "BPU redirect must not coincide with a fetch PC read")
            m.d.sync += next_fetch_addr.eq(pc)
            m.d.sync += next_fetch_addr_v.eq(1)

        @def_method(m, self.ifu_redirect)
        def _(pc, pc_valid):
            m.d.sync += next_fetch_addr.eq(pc)
            m.d.sync += next_fetch_addr_v.eq(pc_valid)

        @def_method(m, self.backend_redirect)
        def _(pc):
            m.d.sync += next_fetch_addr.eq(pc)
            m.d.sync += next_fetch_addr_v.eq(1)

        return m
