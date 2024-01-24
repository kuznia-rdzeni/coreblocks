from typing import Protocol

from amaranth import *
from amaranth.hdl.rec import DIR_FANIN

from coreblocks.peripherals.wishbone import WishboneMaster
from coreblocks.peripherals.axi_lite import AXILiteMaster

from transactron import Method, def_method, TModule
from transactron.utils import HasElaborate
from transactron.lib import Serializer

__all__ = ["BusMasterInterface", "WishboneMasterAdapter", "AXILiteMasterAdapter"]


class BusParametersInterface(Protocol):
    """
    Bus Parameters Interface for common buses

    Parameters
    ----------
    data_width : int
        An integer that describe the width of data for parametrized bus.
    addr_width : int
        An integer that describe the width of address for parametrized bus.
    granularity : int
        An integer that describe the granularity of accesses for parametrized bus.
    """

    data_width: int
    addr_width: int
    granularity: int


class BusMasterInterface(HasElaborate, Protocol):
    """
    Bus Master Interface for common buses.

    The bus interface if preferable way to gain access to specific bus.
    It ease interchangeability of buses on core configuration level.

    Parameters
    ----------
    params : BusParametersInterface
        Object that describe parameters of bus.
    request_read : Method
        A method that is used to send a read request to bus.
    request_write : Method
        A method that is used to send a write request to bus.
    get_read_response : Method
        A method that is used to receive the response from bus for previously sent read request.
    get_write_response : Method
        A method that is used to receive the response from bus for previously sent write request.
    """

    params: BusParametersInterface
    request_read: Method
    request_write: Method
    get_read_response: Method
    get_write_response: Method


class CommonBusMasterMethodLayout:
    """
    Common bus master layouts for methods

    Parameters
    ----------
    bus_params: BusParametersInterface
        Patameters used to generate common bus master layouts.

    Attributes
    ----------
    request_read_layout: Layout
        Layout for request_read method of common bus master.

    request_write_layout: Layout
        Layout for request_write method of common bus master.

    read_response_layout: Layout
        Layout for get_read_response method of common bus master.

    write_response_layout: Layout
        Layout for get_write_response method of common bus master.
    """

    def __init__(self, bus_params: BusParametersInterface):
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


class WishboneMasterAdapter(Elaboratable, BusMasterInterface):
    """
    An adapter for Wishbone master.

    The adapter module is for use in places where BusMasterInterface is expected.

    Parameters
    ----------
    bus: WishboneMaster
        Specific wishbone master module which is to be adapted.

    Attributes
    ----------
    params: BusParametersInterface
        Parameters of the bus.

    method_layouts: CommonBusMasterMethodLayout
        Layouts of common bus master methods.

    request_read: Method
        Transactional method for initiating read request.
        Readiense depends on readiense of wishbone 'request' method.
        Takes 'request_read_layout' as argument.

    request_write: Method
        Transactional method for initiating write request.
        Readiense depends on readiense of wishbone 'request' method.
        Takes 'request_write_layout' as argument.

    get_read_response: Method
        Transactional method for reading response of read action.
        Readiense depends on readiense of wishbone 'result' method.
        Takes 'read_response_layout' as argument.

    get_write_response: Method
        Transactional method for reading response of write action.
        Readiense depends on readiense of wishbone 'result' method.
        Takes 'write_response_layout' as argument.
    """

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

        bus_serializer = Serializer(
            port_count=2, serialized_req_method=self.bus.request, serialized_resp_method=self.bus.result
        )
        m.submodules.bus_serializer = bus_serializer

        @def_method(m, self.request_read)
        def _(arg):
            we = C(0, unsigned(1))
            data = C(0, unsigned(self.params.data_width))
            bus_serializer.serialize_in[0](m, addr=arg.addr, data=data, we=we, sel=arg.sel)

        @def_method(m, self.request_write)
        def _(arg):
            we = C(1, unsigned(1))
            bus_serializer.serialize_in[1](m, addr=arg.addr, data=arg.data, we=we, sel=arg.sel)

        @def_method(m, self.get_read_response)
        def _():
            res = bus_serializer.serialize_out[0](m)
            return {"data": res.data, "err": res.err}

        @def_method(m, self.get_write_response)
        def _():
            res = bus_serializer.serialize_out[1](m)
            return {"err": res.err}

        return m


class AXILiteMasterAdapter(Elaboratable, BusMasterInterface):
    """
    An adapter for AXI Lite master.

    The adapter module is for use in places where BusMasterInterface is expected.

    Parameters
    ----------
    bus: AXILiteMaster
        Specific axi lite master module which is to be adapted.

    Attributes
    ----------
    params: BusParametersInterface
        Parameters of the bus.

    method_layouts: CommonBusMasterMethodLayout
        Layouts of common bus master methods.

    request_read: Method
        Transactional method for initiating read request.
        Readiense depends on readiense of axi lite 'ra_request' method.
        Takes 'request_read_layout' as argument.

    request_write: Method
        Transactional method for initiating write request.
        Readiense depends on readiense of axi lite 'wa_request' and 'wd_request' methods.
        Takes 'request_write_layout' as argument.

    get_read_response: Method
        Transactional method for reading response of read action.
        Readiense depends on readiense of axi lite 'rd_response' method.
        Takes 'read_response_layout' as argument.

    get_write_response: Method
        Transactional method for reading response of write action.
        Readiense depends on readiense of axi lite 'wr_response' method.
        Takes 'write_response_layout' as argument.
    """

    def __init__(self, bus: AXILiteMaster):
        self.bus = bus
        self.params = self.bus.axil_params

        self.method_layouts = CommonBusMasterMethodLayout(self.params)

        self.request_read = Method(i=self.method_layouts.request_read_layout)
        self.request_write = Method(i=self.method_layouts.request_write_layout)
        self.get_read_response = Method(o=self.method_layouts.read_response_layout)
        self.get_write_response = Method(o=self.method_layouts.write_response_layout)

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
            err = res.resp != 0
            return {"data": res.data, "err": err}

        @def_method(m, self.get_write_response)
        def _():
            res = self.bus.wr_response(m)
            err = res.resp != 0
            return {"err": err}

        return m
