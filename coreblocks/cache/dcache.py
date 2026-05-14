from amaranth import *
from amaranth.utils import exact_log2
from transactron.core import def_method, TModule
from transactron import Method
from coreblocks.params import DCacheParameters
from coreblocks.interface.layouts import DCacheLayouts
from transactron.lib import *
from transactron.utils import logging
from coreblocks.peripherals.bus_adapter import BusMasterInterface
from coreblocks.cache.iface import CacheInterface

__all__ = ["DCacheBypass"]

log = logging.HardwareLogger("backend.dcache")


class DCacheBypass(Elaboratable, CacheInterface):
    def __init__(self, layouts: DCacheLayouts, params: DCacheParameters, bus_master: BusMasterInterface):
        self.layouts = layouts
        self.params = params
        self.bus_master = bus_master

        self.issue_req = Method(i=layouts.issue_req)
        self.accept_res = Method(o=layouts.accept_res)
        self.flush = Method()

    def elaborate(self, platform):
        m = TModule()

        is_last_store = Signal()

        @def_method(m, self.issue_req)
        def _(paddr: Value, data: Value, byte_mask: Value, store: Value):
            bus_addr = paddr >> exact_log2(self.params.word_width_bytes)

            with condition(m) as branch:
                with branch(store):
                    self.bus_master.request_write(m, addr=bus_addr, data=data, sel=byte_mask)
                with branch():
                    self.bus_master.request_read(m, addr=bus_addr, sel=byte_mask)

            m.d.sync += is_last_store.eq(store)

        @def_method(m, self.accept_res)
        def _():
            data = Signal(self.params.word_width)
            err = Signal()

            with condition(m) as branch:
                with branch(is_last_store):
                    res = self.bus_master.get_write_response(m)
                    m.d.comb += err.eq(res.err)
                with branch():
                    res = self.bus_master.get_read_response(m)
                    m.d.comb += [err.eq(res.err), data.eq(res.data)]

            return {"data": data, "error": err}

        @def_method(m, self.flush)
        def _():
            pass

        return m
