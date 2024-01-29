from amaranth import *
from transactron import Method, def_method, TModule
from transactron.utils import assign
from coreblocks.peripherals.bus_adapter import BusMasterInterface, CommonBusMasterMethodLayout


class MockBusParameteres:
    def __init__(self, data_width: int, addr_width: int, granularity: int = 8):
        self.data_width: int = data_width
        self.addr_width: int = addr_width
        self.granularity: int = granularity


class BusMasterMock(Elaboratable, BusMasterInterface):
    """
    A mock of common bus master.

    Attributes
    ----------
    params: BusParametersInterface
        Parameters of the mocked bus.

    method_layouts: CommonBusMasterMethodLayout
        Layouts of common bus master methods.

    request_read: Method
        Transactional method for initiating read request.
        Takes 'request_read_layout' as argument.

    request_write: Method
        Transactional method for initiating write request.
        Takes 'request_write_layout' as argument.

    get_read_response: Method
        Transactional method for reading response of read action.
        Takes 'read_response_layout' as argument.

    get_write_response: Method
        Transactional method for reading response of write action.
        Takes 'write_response_layout' as argument.
    """

    def __init__(self, params: MockBusParameteres):
        self.params = params

        self.method_layouts = CommonBusMasterMethodLayout(self.params)

        self.request_read = Method(i=self.method_layouts.request_read_layout)
        self.request_write = Method(i=self.method_layouts.request_write_layout)
        self.get_read_response = Method(o=self.method_layouts.read_response_layout)
        self.get_write_response = Method(o=self.method_layouts.write_response_layout)

        self.read_request_pending = Signal()
        self.write_request_pending = Signal()
        self.read_request_response_prep = Signal()
        self.write_request_response_prep = Signal()
        self.request_read_rec = Record(self.method_layouts.request_read_layout)
        self.request_write_rec = Record(self.method_layouts.request_write_layout)
        self.read_response_rec = Record(self.method_layouts.read_response_layout)
        self.write_response_rec = Record(self.method_layouts.write_response_layout)

    def activate(self):
        yield self.read_request_pending.eq(0)
        yield self.write_request_pending.eq(0)
        yield self.read_request_response_prep.eq(0)
        yield self.write_request_response_prep.eq(0)

    def wait_for_read_request(self):
        while not (yield self.read_request_pending):
            yield

    def wait_for_write_request(self):
        while not (yield self.write_request_pending):
            yield

    def verify_read_request(self, exp_addr, exp_sel):
        assert (yield self.read_request_pending)
        assert (yield self.request_read_rec.addr) == exp_addr
        assert (yield self.request_read_rec.sel) == exp_sel

    def verify_write_request(self, exp_addr, exp_sel, exp_data):
        assert (yield self.write_request_pending)
        assert (yield self.request_write_rec.addr) == exp_addr
        assert (yield self.request_write_rec.sel) == exp_sel
        assert (yield self.request_write_rec.data) == exp_data

    def respond_to_read_request(self, resp_data, resp_err):
        assert (yield self.read_request_pending)
        yield self.read_response_rec.data.eq(resp_data)
        yield self.read_response_rec.err.eq(resp_err)
        yield self.read_request_response_prep.eq(1)
        yield
        yield self.read_request_response_prep.eq(0)

    def respond_to_write_request(self, resp_err):
        assert (yield self.write_request_pending)
        yield self.read_response_rec.err.eq(resp_err)
        yield self.write_request_response_prep.eq(1)
        yield
        yield self.write_request_response_prep.eq(0)

    def elaborate(self, platform):
        m = TModule()

        @def_method(m, self.request_read, ~self.read_request_pending)
        def _(arg):
            m.d.sync += assign(self.request_read_rec, arg)
            m.d.sync += self.read_request_pending.eq(1)

        @def_method(m, self.request_write, ~self.write_request_pending)
        def _(arg):
            m.d.sync += assign(self.request_write_rec, arg)
            m.d.sync += self.write_request_pending.eq(1)

        @def_method(m, self.get_read_response, self.read_request_response_prep)
        def _():
            m.d.sync += self.read_request_pending.eq(0)
            return self.read_response_rec

        @def_method(m, self.get_write_response, self.write_request_response_prep)
        def _():
            m.d.sync += self.write_request_pending.eq(0)
            return self.write_response_rec

        return m
