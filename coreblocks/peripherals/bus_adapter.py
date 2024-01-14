from typing import TypeAlias
from enum import Enum
from amaranth import *
from amaranth.hdl.rec import DIR_FANIN
from transactron import Method, def_method, TModule
from coreblocks.peripherals.wishbone import WishboneMaster
from coreblocks.peripherals.axi_lite import AXILiteMaster

__all__ = ["BusMasterAdapter"]


BusMasterLike: TypeAlias = WishboneMaster | AXILiteMaster


class BusMasterType(Enum):
    """ """

    Wishbone = (1,)
    AXILite = (2,)

    @staticmethod
    def map_bus_type(bus: BusMasterLike) -> "BusMasterType":
        if isinstance(bus, WishboneMaster):
            return BusMasterType.Wishbone
        if isinstance(bus, AXILiteMaster):
            return BusMasterType.AXILite
        raise TypeError("Bus master instance not handled")


class CommonBusMasterMethodLayout:
    """ """

    def __init__(self, bus_params):
        self.bus_params = bus_params

        self.request_read_layout = [
            ("addr", self.bus_params.addr_width, DIR_FANIN),
            ("sel", self.bus_params.data_width // self.bus_params.granularity, DIR_FANIN),
            ("prot", 3, DIR_FANIN),
        ]

        self.request_write_layout = [
            ("addr", self.bus_params.addr_width, DIR_FANIN),
            ("data", self.bus_params.data_width, DIR_FANIN),
            ("sel", self.bus_params.data_width // self.bus_params.granularity, DIR_FANIN),
            ("prot", 3, DIR_FANIN),
            ("strb", self.bus_params.data_width // 8, DIR_FANIN),
        ]

        self.read_response_layout = [("data", self.bus_params.data_width), ("err", 1)]

        self.write_response_layout = [("err", 1)]


class BusMasterAdapter(Elaboratable):
    """ """

    def __init__(self, bus):
        self.bus = bus
        self.params = self.bus.params

        self.bus_type = BusMasterType.map_bus_type(self.bus)
        self.method_layouts = CommonBusMasterMethodLayout(self.params)

        self.request_read = Method(i=self.method_layouts.request_read_layout)
        self.request_write = Method(i=self.method_layouts.request_write_layout)
        self.get_read_response = Method(o=self.method_layouts.read_response_layout)
        self.get_write_response = Method(o=self.method_layouts.write_response_layout)

    def def_wishbone_methods(self, m: TModule):
        if self.bus_type != BusMasterType.Wishbone:
            return

        @def_method(m, self.request_read)
        def _(arg):
            we = C(0, unsigned(1))
            data = C(0, unsigned(self.bus.params.data_width))
            self.bus.request(m, addr=arg.addr, sel=arg.sel, we=we, data=data)

        @def_method(m, self.request_write)
        def _(arg):
            we = C(1, unsigned(1))
            self.bus.request(m, addr=arg.addr, sel=arg.sel, we=we, data=arg.data)

        @def_method(m, self.get_read_response)
        def _():
            res = self.bus.result(m)
            return {"data": res.data, "err": res.err}

        @def_method(m, self.get_write_response)
        def _():
            res = self.bus.result(m)
            return {"err": res.err}

    def def_axi_lite_methods(self, m: TModule):
        if self.bus_type != BusMasterType.AXILite:
            return

        @def_method(m, self.request_read)
        def _(arg):
            self.bus.ra_request(m, addr=arg.addr, prot=arg.prot)

        @def_method(m, self.request_write)
        def _(arg):
            self.bus.wa_request(m, addr=arg.addr, prot=arg.prot)
            self.bus.wd_request(m, data=arg.data, strb=arg.strb)

        @def_method(m, self.get_read_response)
        def _():
            err = Signal(1)
            res = self.bus.rd_response(m)

            with m.Switch(res.resp):
                with m.Case(0):
                    m.d.comb += err.eq(0)
                with m.Default():
                    m.d.comb += err.eq(1)

            return {"data": res.data, "err": err}

        @def_method(m, self.get_write_response)
        def _():
            err = Signal(1)
            res = self.bus.wr_response(m)

            with m.Switch(res.resp):
                with m.Case(0):
                    m.d.comb += err.eq(0)
                with m.Default():
                    m.d.comb += err.eq(1)

            return {"err": err}

    def elaborate(self, platform):
        m = TModule()

        self.def_wishbone_methods(m)
        self.def_axi_lite_methods(m)

        return m
