from typing import Protocol

from amaranth import *
from amaranth.hdl.rec import DIR_FANIN

from coreblocks.peripherals.wishbone import WishboneMaster
from coreblocks.peripherals.axi_lite import AXILiteMaster

from transactron import Method, def_method, TModule
from transactron.utils import HasElaborate


__all__ = ["BusMasterInterface", "WishboneMasterAdapter", "AXILiteMasterAdapter"]


class BusParametersInterface(Protocol):
    """"""

    data_width: int
    addr_width: int
    granularity: int


class CommonBusMasterMethodLayout:
    """ """

    def __init__(self, bus_params):
        self.bus_params = bus_params

        self.request_read_layout = [
            ("addr", self.bus_params.addr_width, DIR_FANIN),
            ("sel", self.bus_params.data_width // self.bus_params.granularity, DIR_FANIN),
        ]

        self.request_write_layout = [
            ("addr", self.bus_params.addr_width, DIR_FANIN),
            ("data", self.bus_params.data_width, DIR_FANIN),
            ("sel", self.bus_params.data_width // self.bus_params.granularity, DIR_FANIN),
        ]

        self.read_response_layout = [("data", self.bus_params.data_width), ("err", 1)]

        self.write_response_layout = [("err", 1)]


class BusMasterInterface(HasElaborate, Protocol):
    """"""

    params: BusParametersInterface
    request_read: Method
    request_write: Method
    get_read_response: Method
    get_write_response: Method


class WishboneMasterAdapter(Elaboratable, BusMasterInterface):
    """"""

    def __init__(self, bus: WishboneMaster):
        self.bus = bus
        self.params = self.bus.wb_params

        self.method_layouts = CommonBusMasterMethodLayout(self.params)

        self.request_read = Method(i=self.method_layouts.request_read_layout)
        self.request_write = Method(i=self.method_layouts.request_write_layout)
        self.get_read_response = Method(o=self.method_layouts.read_response_layout)
        self.get_write_response = Method(o=self.method_layouts.write_response_layout)

    def elaborate(self, platform):
        m = TModule()

        @def_method(m, self.request_read)
        def _(arg):
            we = C(0, unsigned(1))
            data = C(0, unsigned(self.params.data_width))
            self.bus.request(m, addr=arg.addr, data=data, we=we, sel=arg.sel)

        @def_method(m, self.request_write)
        def _(arg):
            we = C(1, unsigned(1))
            self.bus.request(m, addr=arg.addr, data=arg.data, we=we, sel=arg.sel)

        @def_method(m, self.get_read_response)
        def _():
            res = self.bus.result(m)
            return {"data": res.data, "err": res.err}

        @def_method(m, self.get_write_response)
        def _():
            res = self.bus.result(m)
            return {"err": res.err}

        return m


class AXILiteMasterAdapter(Elaboratable, BusMasterInterface):
    """"""

    def __init__(self, bus: AXILiteMaster):
        self.bus = bus
        self.params = self.bus.axil_params

        self.method_layouts = CommonBusMasterMethodLayout(self.params)

        self.request_read = Method(i=self.method_layouts.request_read_layout)
        self.request_write = Method(i=self.method_layouts.request_write_layout)
        self.get_read_response = Method(o=self.method_layouts.read_response_layout)
        self.get_write_response = Method(o=self.method_layouts.write_response_layout)

    def deduce_err(self, m: TModule, resp: Value):
        err = Signal(1)

        with m.Switch(resp):
            with m.Case(0):
                m.d.comb += err.eq(0)
            with m.Default():
                m.d.comb += err.eq(1)

        return err

    def elaborate(self, platform):
        m = TModule()

        @def_method(m, self.request_read)
        def _(arg):
            prot = C(0, unsigned(3))
            self.bus.ra_request(m, addr=arg.addr, prot=prot)

        @def_method(m, self.request_write)
        def _(arg):
            prot = C(0, unsigned(3))
            self.bus.wa_request(m, addr=arg.addr, prot=prot)
            self.bus.wd_request(m, data=arg.data, strb=arg.sel)

        @def_method(m, self.get_read_response)
        def _():
            res = self.bus.rd_response(m)
            err = self.deduce_err(m, res.resp)
            return {"data": res.data, "err": err}

        @def_method(m, self.get_write_response)
        def _():
            res = self.bus.wr_response(m)
            err = self.deduce_err(m, res.resp)
            return {"err": err}

        return m
