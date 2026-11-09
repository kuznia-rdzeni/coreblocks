from typing import Protocol

from amaranth import *

from coreblocks.peripherals.wishbone import WishboneMasterMethodLayout, WishboneParameters
from coreblocks.peripherals.axi_lite import AXILiteMasterInterface, AXILiteMasterMethods, AXILiteParameters

from transactron import Method, Provided, Required, def_method, def_methods, TModule
from transactron.lib import RequestResponseInterface, Serializer
from transactron.utils.transactron_helpers import make_layout

__all__ = [
    "BusParametersInterface",
    "BusMasterInterface",
    "BusMasterMethods",
    "WishboneMasterAdapter",
    "AXILiteMasterAdapter",
]


class BusParametersInterface(Protocol):
    """
    An interface for parameters of a common bus.

    Parameters
    ----------
    data_width : int
        An integer that describes the data width of a parametrized bus.
    addr_width : int
        An integer that describes the address width of a parametrized bus.
    granularity : int
        An integer that describes the granularity of accesses of a parametrized bus.
    """

    data_width: int
    addr_width: int
    granularity: int


class BusMasterInterface(Protocol):
    """
    An interface of a common bus.

    The bus interface is the preferred way to gain access to a specific bus.
    It simplifies interchangeability of buses on the core configuration level.
    """

    params: BusParametersInterface
    """Parameters of the bus."""

    request_read: Provided[Method]
    """A method that is used to send a read request to a bus.
    Input layout is `CommonBusMasterMethodLayout.request_read_layout`."""

    request_write: Provided[Method]
    """A method that is used to send a write request to a bus.
    Input layout is `CommonBusMasterMethodLayout.request_write_layout`."""

    get_read_response: Provided[Method]
    """A method that is used to receive a response from a bus for a previously sent read request.
    Output layout is `CommonBusMasterMethodLayout.read_response_layout`."""

    get_write_response: Provided[Method]
    """A method that is used to receive a response from a bus for a previously sent write request.
    Output layout is `CommonBusMasterMethodLayout.write_response_layout`."""


class CommonBusMasterMethodLayout:
    """
    Layouts of methods for a common bus master.

    Parameters
    ----------
    bus_params: BusParametersInterface
        Parameters used to generate common bus master methods layouts.

    Attributes
    ----------
    request_read_layout: Layout
        A layout for the `request_read` method of a common bus master.

    request_write_layout: Layout
        A layout for the `request_write` method of a common bus master.

    read_response_layout: Layout
        A layout for the `get_read_response` method of a common bus master.

    write_response_layout: Layout
        A layout for the `get_write_response` method of a common bus master.
    """

    def __init__(self, bus_params: BusParametersInterface):
        self.bus_params = bus_params

        self.request_read_layout = make_layout(
            ("addr", self.bus_params.addr_width),
            ("sel", self.bus_params.data_width // self.bus_params.granularity),
        )

        self.request_write_layout = make_layout(
            ("addr", self.bus_params.addr_width),
            ("data", self.bus_params.data_width),
            ("sel", self.bus_params.data_width // self.bus_params.granularity),
        )

        self.read_response_layout = make_layout(("data", self.bus_params.data_width), ("err", 1))

        self.write_response_layout = make_layout(("err", 1))


class BusMasterMethods(BusMasterInterface):
    """Fresh, undefined `BusMasterInterface` methods."""

    def __init__(self, params: BusParametersInterface):
        self.params = params
        self.method_layouts = CommonBusMasterMethodLayout(params)

        self.request_read = Method(i=self.method_layouts.request_read_layout)
        self.request_write = Method(i=self.method_layouts.request_write_layout)
        self.get_read_response = Method(o=self.method_layouts.read_response_layout)
        self.get_write_response = Method(o=self.method_layouts.write_response_layout)


class WishboneMasterAdapter(Elaboratable):
    """
    An adapter for Wishbone master.

    Parameters
    ----------
    wb_params: WishboneParameters
        Parameters of the adapted Wishbone master.

    port_count: int
        Number of ports to be created for the bus adapter. Each port will have its own set
        of methods for read and write requests and responses. The default value is 1.

    Attributes
    ----------
    params: BusParametersInterface
        Parameters of the bus.

    method_layouts: CommonBusMasterMethodLayout
        Layouts of common bus master methods.

    """

    bus: Required[RequestResponseInterface]
    """Wishbone master which is adapted."""

    ports: Provided[list[BusMasterInterface]]
    """List of bus master interfaces for each port. Each interface contains methods for read and write requests
    and responses. The number of interfaces is equal to `port_count`."""

    def __init__(self, wb_params: WishboneParameters, port_count: int = 1):
        self.params = wb_params

        self.method_layouts = CommonBusMasterMethodLayout(self.params)

        self.port_count = port_count

        wb_layouts = WishboneMasterMethodLayout(wb_params)
        self.serializer = Serializer(
            port_count=2 * port_count,
            req_layout=wb_layouts.request_layout,
            resp_layout=wb_layouts.response_layout,
        )
        self.bus = self.serializer.server

        self.ports = [BusMasterMethods(self.params) for _ in range(port_count)]

    def elaborate(self, platform):
        m = TModule()

        m.submodules.bus_serializer = bus_serializer = self.serializer

        @def_methods(m, [port.request_read for port in self.ports])
        def _(i, arg):
            we = C(0, unsigned(1))
            data = C(0, unsigned(self.params.data_width))
            bus_serializer.ports[0 + 2 * i].request(m, addr=arg.addr, data=data, we=we, sel=arg.sel)

        @def_methods(m, [port.request_write for port in self.ports])
        def _(i, arg):
            we = C(1, unsigned(1))
            bus_serializer.ports[1 + 2 * i].request(m, addr=arg.addr, data=arg.data, we=we, sel=arg.sel)

        @def_methods(m, [port.get_read_response for port in self.ports])
        def _(i):
            res = bus_serializer.ports[0 + 2 * i].response(m)
            return {"data": res.data, "err": res.err}

        @def_methods(m, [port.get_write_response for port in self.ports])
        def _(i):
            res = bus_serializer.ports[1 + 2 * i].response(m)
            return {"err": res.err}

        return m


class AXILiteMasterAdapter(BusMasterMethods, Elaboratable):
    """
    An adapter for AXI Lite master.

    The adapter module is for use in places where BusMasterInterface is expected.

    Parameters
    ----------
    axil_params: AXILiteParameters
        Parameters of the adapted AXI Lite master.

    Attributes
    ----------
    params: BusParametersInterface
        Parameters of the bus.

    method_layouts: CommonBusMasterMethodLayout
        Layouts of common bus master methods.

    request_read: Method
        Transactional method for initiating a read request.
        It is ready if the `ra_request` method of the underlying AXI Lite master is ready.
        Input layout is `request_read_layout`.

    request_write: Method
        Transactional method for initiating a write request.
        It is ready if the 'wa_request' and 'wd_request' methods of the underlying AXI Lite master are ready.
        Input layout is `request_write_layout`.

    get_read_response: Method
        Transactional method for reading a response of a read action.
        It is ready if the `rd_response` method of the underlying AXI Lite master is ready.
        Output layout is `read_response_layout`.

    get_write_response: Method
        Transactional method for reading a response of a write action.
        It is ready if the `wr_response` method of the underlying AXI Lite master is ready.
        Output layout is `write_response_layout`.
    """

    bus: Required[AXILiteMasterInterface]
    """AXI Lite master which is adapted."""

    def __init__(self, axil_params: AXILiteParameters):
        super().__init__(axil_params)
        self.bus = AXILiteMasterMethods(axil_params)

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
