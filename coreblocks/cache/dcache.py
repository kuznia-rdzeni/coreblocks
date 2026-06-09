from amaranth import *
from amaranth.utils import exact_log2
from transactron.core import def_method, TModule
from transactron import Method
from coreblocks.params import DCacheParameters
from coreblocks.interface.layouts import DCacheLayouts
from transactron.lib import *
from transactron.utils import logging
from coreblocks.peripherals.bus_adapter import BusMasterInterface
from coreblocks.cache.iface import DCacheInterface

__all__ = ["DCacheBypass"]

log = logging.HardwareLogger("backend.dcache")


class DCacheBypass(Elaboratable, DCacheInterface):
    def __init__(self, layouts: DCacheLayouts, params: DCacheParameters, bus_master: BusMasterInterface):
        if bus_master.params.granularity != 8:
            raise ValueError("Granularity for data cache bus has to be 8")

        self.layouts = layouts
        self.params = params
        self.bus_master = bus_master

        self.issue_read = Method(i=layouts.issue_read)
        self.issue_store = Method(i=layouts.issue_store)
        self.accept_read = Method(o=layouts.accept_read)
        self.accept_store = Method(o=layouts.accept_store)
        self.flush = Method()

    def elaborate(self, platform):
        m = TModule()

        word_shift = exact_log2(self.params.word_width_bytes)

        @def_method(m, self.issue_read)
        def _(paddr: Value, byte_mask: Value):
            self.bus_master.request_read(m, addr=paddr >> word_shift, sel=byte_mask)

        @def_method(m, self.issue_store)
        def _(paddr: Value, data: Value, byte_mask: Value):
            self.bus_master.request_write(m, addr=paddr >> word_shift, data=data, sel=byte_mask)

        @def_method(m, self.accept_read)
        def _():
            res = self.bus_master.get_read_response(m)
            return {"data": res.data, "error": res.err}

        @def_method(m, self.accept_store)
        def _():
            res = self.bus_master.get_write_response(m)
            return {"error": res.err}

        @def_method(m, self.flush)
        def _():
            pass

        return m
