from typing import Protocol, TypeAlias, runtime_checkable
from amaranth import *
from amaranth.lib.wiring import Component, Signature, In, Out
from transactron import Method, def_method, TModule
from transactron.core import Transaction
from transactron.lib.connectors import Forwarder
from transactron.utils._typing import AbstractInterface, AbstractSignature

__all__ = ["AXILiteParameters", "AXILiteSignature", "AXILiteInterface", "AXILiteMaster"]


class AXILiteParameters:
    """Parameters of the AXI-Lite bus.

    Parameters
    ----------
    data_width: int
        Width of "data" signals for "write data" and "read data" channels. Must be either 32 or 64 bits. Defaults to 64
    addr_width: int
        Width of "addr" signals for "write address" and "read address" channels. Defaults to 64 bits.
    """

    def __init__(self, *, data_width: int = 64, addr_width: int = 64):
        self.data_width = data_width
        self.addr_width = addr_width
        self.granularity = 8


class AXILiteSignature(Signature):
    """AXI-Lite bus signature

    Parameters
    ----------
    axil_params: AXILiteParameters
        Parameters used to generate AXI-Lite signature
    """

    def __init__(self, axil_params: AXILiteParameters):
        write_address = Signature(
            {
                "valid": Out(1),
                "rdy": In(1),
                "addr": Out(axil_params.addr_width),
                "prot": Out(3),
            }
        )

        write_data = Signature(
            {
                "valid": Out(1),
                "rdy": In(1),
                "data": Out(axil_params.data_width),
                "strb": Out(axil_params.data_width // 8),
            }
        )

        write_response = Signature(
            {
                "valid": In(1),
                "rdy": Out(1),
                "resp": In(2),
            }
        )

        read_address = Signature(
            {
                "valid": Out(1),
                "rdy": In(1),
                "addr": Out(axil_params.addr_width),
                "prot": Out(3),
            }
        )

        read_data = Signature(
            {
                "valid": In(1),
                "rdy": Out(1),
                "data": In(axil_params.data_width),
                "resp": In(2),
            }
        )

        super().__init__(
            {
                "write_address": Out(write_address),
                "write_data": Out(write_data),
                "write_response": Out(write_response),
                "read_address": Out(read_address),
                "read_data": Out(read_data),
            }
        )


class AXILiteWriteAddressInterface(AbstractInterface[AbstractSignature], Protocol):
    valid: Signal
    rdy: Signal
    addr: Signal
    prot: Signal


class AXILiteWriteDataInterface(AbstractInterface[AbstractSignature], Protocol):
    valid: Signal
    rdy: Signal
    data: Signal
    strb: Signal


class AXILiteWriteResponseInterface(AbstractInterface[AbstractSignature], Protocol):
    valid: Signal
    rdy: Signal
    resp: Signal


class AXILiteReadAddressInterface(AbstractInterface[AbstractSignature], Protocol):
    valid: Signal
    rdy: Signal
    addr: Signal
    prot: Signal


@runtime_checkable
class AXILiteReadDataInterface(AbstractInterface[AbstractSignature], Protocol):
    valid: Signal
    rdy: Signal
    data: Signal
    resp: Signal


class AXILiteInterface(AbstractInterface[AbstractSignature], Protocol):
    write_address: AXILiteWriteAddressInterface
    write_data: AXILiteWriteDataInterface
    write_response: AXILiteWriteResponseInterface
    read_address: AXILiteReadAddressInterface
    read_data: AXILiteReadDataInterface


AXILiteOutChannel: TypeAlias = AXILiteWriteAddressInterface | AXILiteWriteDataInterface | AXILiteReadAddressInterface
AXILiteInChannel: TypeAlias = AXILiteWriteResponseInterface | AXILiteReadDataInterface


class AXILiteMasterMethodLayouts:
    """AXI-Lite master layouts for methods

    Parameters
    ----------
    axil_params: AXILiteParameters
        Parameters used to generate AXI-Lite master layouts

    Attributes
    ----------
    ra_request_layout: Layout
        Layout for ra_request method of AXILiteMaster.

    wa_request_layout: Layout
        Layout for wa_request method of AXILiteMaster.

    wd_request_layout: Layout
        Layout for wd_request method of AXILiteMaster.

    rd_response_layout: Layout
        Layout for rd_response method of AXILiteMaster.

    wr_response_layout: Layout
        Layout for wr_response method of AXILiteMaster.
    """

    def __init__(self, axil_params: AXILiteParameters):
        self.ra_request_layout = [
            ("addr", axil_params.addr_width),
            ("prot", 3),
        ]

        self.wa_request_layout = [
            ("addr", axil_params.addr_width),
            ("prot", 3),
        ]

        self.wd_request_layout = [
            ("data", axil_params.data_width),
            ("strb", axil_params.data_width // 8),
        ]

        self.rd_response_layout = [
            ("data", axil_params.data_width),
            ("resp", 2),
        ]

        self.wr_response_layout = [
            ("resp", 2),
        ]


class AXILiteMaster(Component):
    """AXI-Lite master interface.

    Parameters
    ----------
    axil_params: AXILiteParameters
        Parameters for bus generation.

    Attributes
    ----------
    ra_request: Method
        Transactional method for initiating request on read address channel.
        Ready when no request or only one is being executed.
        Takes 'ra_request_layout' as argument.

    rd_response: Method
        Transactional method for reading response from read data channel.
        Ready when there is request response availabe.
        Returns data and response state as 'rd_response_layout'.

    wa_request: Method
        Transactional method for initiating request on write address channel.
        Ready when no request or only one is being executed.
        Takes 'wa_request_layout' as argument.

    wd_request: Method
        Transactional method for initiating request on write data channel.
        Ready when no request or only one is being executed.
        Takes 'wd_request_layout' as argument.

    wr_response: Method
        Transactional method for reading response from write response channel.
        Ready when there is request response availabe.
        Returns response state as 'wr_response_layout'.
    """

    axil_master: AXILiteInterface

    def __init__(self, axil_params: AXILiteParameters):
        super().__init__({"axil_master": Out(AXILiteSignature(axil_params))})
        self.axil_params = axil_params

        self.method_layouts = AXILiteMasterMethodLayouts(self.axil_params)

        self.ra_request = Method(i=self.method_layouts.ra_request_layout)
        self.rd_response = Method(o=self.method_layouts.rd_response_layout)
        self.wa_request = Method(i=self.method_layouts.wa_request_layout)
        self.wd_request = Method(i=self.method_layouts.wd_request_layout)
        self.wr_response = Method(o=self.method_layouts.wr_response_layout)

    def start_request_transaction(self, m, arg, *, channel, is_address_channel):
        if is_address_channel:
            m.d.sync += channel.addr.eq(arg.addr)
            m.d.sync += channel.prot.eq(arg.prot)
        else:
            m.d.sync += channel.data.eq(arg.data)
            m.d.sync += channel.strb.eq(arg.strb)
        m.d.sync += channel.valid.eq(1)

    def state_machine_request(self, m: TModule, method: Method, *, channel: AXILiteOutChannel, request_signal: Signal):
        with m.FSM("Idle"):
            with m.State("Idle"):
                m.d.sync += channel.valid.eq(0)
                m.d.comb += request_signal.eq(1)
                with m.If(method.run):
                    m.next = "Active"

            with m.State("Active"):
                with m.If(channel.rdy):
                    m.d.comb += request_signal.eq(1)
                    with m.If(~method.run):
                        m.d.sync += channel.valid.eq(0)
                        m.next = "Idle"
                with m.Else():
                    m.d.comb += request_signal.eq(0)

    def result_handler(self, m: TModule, forwarder: Forwarder, *, channel: AXILiteInChannel):
        with m.If(channel.rdy & channel.valid):
            m.d.sync += channel.rdy.eq(forwarder.read.run)
            with Transaction().body(m):
                if isinstance(channel, AXILiteReadDataInterface):
                    forwarder.write(m, data=channel.data, resp=channel.resp)
                else:
                    forwarder.write(m, resp=channel.resp)
        with m.Else():
            m.d.sync += channel.rdy.eq(forwarder.write.ready)

    def elaborate(self, platform):
        m = TModule()

        m.submodules.rd_forwarder = rd_forwarder = Forwarder(self.method_layouts.rd_response_layout)
        m.submodules.wr_forwarder = wr_forwarder = Forwarder(self.method_layouts.wr_response_layout)

        ra_request_ready = Signal()
        wa_request_ready = Signal()
        wd_request_ready = Signal()
        # read_address
        self.state_machine_request(
            m,
            self.ra_request,
            channel=self.axil_master.read_address,
            request_signal=ra_request_ready,
        )

        @def_method(m, self.ra_request, ready=ra_request_ready)
        def _(arg):
            self.start_request_transaction(m, arg, channel=self.axil_master.read_address, is_address_channel=True)

        # read_data
        self.result_handler(m, rd_forwarder, channel=self.axil_master.read_data)

        @def_method(m, self.rd_response)
        def _():
            return rd_forwarder.read(m)

        # write_adress
        self.state_machine_request(
            m,
            self.wa_request,
            channel=self.axil_master.write_address,
            request_signal=wa_request_ready,
        )

        @def_method(m, self.wa_request, ready=wa_request_ready)
        def _(arg):
            self.start_request_transaction(m, arg, channel=self.axil_master.write_address, is_address_channel=True)

        # write_data
        self.state_machine_request(
            m,
            self.wd_request,
            channel=self.axil_master.write_data,
            request_signal=wd_request_ready,
        )

        @def_method(m, self.wd_request, ready=wd_request_ready)
        def _(arg):
            self.start_request_transaction(m, arg, channel=self.axil_master.write_data, is_address_channel=False)

        # write_response
        self.result_handler(m, wr_forwarder, channel=self.axil_master.write_response)

        @def_method(m, self.wr_response)
        def _():
            return wr_forwarder.read(m)

        return m
