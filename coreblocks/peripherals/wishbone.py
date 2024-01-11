from amaranth import *
from amaranth.hdl.rec import DIR_FANIN, DIR_FANOUT
from amaranth.lib.scheduler import RoundRobin
from functools import reduce
from typing import List
import operator

from transactron import Method, def_method, TModule
from transactron.core import Transaction
from transactron.lib import AdapterTrans, BasicFifo
from transactron.utils import OneHotSwitchDynamic, assign
from transactron.lib.connectors import Forwarder
from transactron.utils.transactron_helpers import from_method_layout


class WishboneParameters:
    """Parameters of the Wishbone bus.

    Parameters
    ----------
    data_width: int
        Width of dat_r and dat_w Wishbone signals. Defaults to 64 bits
    addr_width: int
        Width of adr Wishbone singal. Defaults to 64 bits
    granularity: int
        The smallest unit of data transfer that a port is capable of transferring. Defaults to 8 bits
    """

    def __init__(self, *, data_width=64, addr_width=64, granularity=8):
        self.data_width = data_width
        self.addr_width = addr_width
        self.granularity = granularity


class WishboneLayout:
    """Wishbone bus Layout generator.

    Parameters
    ----------
    wb_params: WishboneParameters
        Parameters used to generate Wishbone layout
    master: Boolean
        Whether the layout should be generated for the master side
        (otherwise it's generated for the slave side)

    Attributes
    ----------
    wb_layout: Record
        Record of a Wishbone bus.
    """

    def __init__(self, wb_params: WishboneParameters, master=True):
        self.wb_layout = [
            ("dat_r", wb_params.data_width, DIR_FANIN if master else DIR_FANOUT),
            ("dat_w", wb_params.data_width, DIR_FANOUT if master else DIR_FANIN),
            ("rst", 1, DIR_FANOUT if master else DIR_FANIN),
            ("ack", 1, DIR_FANIN if master else DIR_FANOUT),
            ("adr", wb_params.addr_width, DIR_FANOUT if master else DIR_FANIN),
            ("cyc", 1, DIR_FANOUT if master else DIR_FANIN),
            ("stall", 1, DIR_FANIN if master else DIR_FANOUT),
            ("err", 1, DIR_FANIN if master else DIR_FANOUT),
            ("lock", 1, DIR_FANOUT if master else DIR_FANIN),
            ("rty", 1, DIR_FANIN if master else DIR_FANOUT),
            ("sel", wb_params.data_width // wb_params.granularity, DIR_FANOUT if master else DIR_FANIN),
            ("stb", 1, DIR_FANOUT if master else DIR_FANIN),
            ("we", 1, DIR_FANOUT if master else DIR_FANIN),
        ]


class WishboneBus(Record):
    """Wishbone bus.

    Parameters
    ----------
    wb_params: WishboneParameters
        Parameters for bus generation.
    """

    def __init__(self, wb_params: WishboneParameters, **kwargs):
        super().__init__(WishboneLayout(wb_params).wb_layout, **kwargs)


class WishboneMaster(Elaboratable):
    """Wishbone bus master interface.

    Parameters
    ----------
    wb_params: WishboneParameters
        Parameters for bus generation.

    Attributes
    ----------
    wbMaster: Record (like WishboneLayout)
        Wishbone bus output.
    request: Method
        Transactional method to start a new Wishbone request.
        Ready when no request is being executed and previous result is read.
        Takes `requestLayout` as argument.
    result: Method
        Transactional method to read previous request result.
        Becomes ready after Wishbone request is completed.
        Returns state of request (error or success) and data (in case of read request) as `resultLayout`.
    """

    def __init__(self, wb_params: WishboneParameters):
        self.wb_params = wb_params
        self.wb_layout = WishboneLayout(wb_params).wb_layout
        self.wbMaster = Record(self.wb_layout)
        self.generate_layouts(wb_params)

        self.request = Method(i=self.requestLayout)
        self.result = Method(o=self.resultLayout)

        self.result_data = Signal(from_method_layout(self.resultLayout))

        # latched input signals
        self.txn_req = Signal(from_method_layout(self.requestLayout))

        self.ports = list(self.wbMaster.fields.values())

    def generate_layouts(self, wb_params: WishboneParameters):
        # generate method layouts locally
        self.requestLayout = [
            ("addr", wb_params.addr_width),
            ("data", wb_params.data_width),
            ("we", 1),
            ("sel", wb_params.data_width // wb_params.granularity),
        ]

        self.resultLayout = [("data", wb_params.data_width), ("err", 1)]

    def elaborate(self, platform):
        m = TModule()

        m.submodules.result = result = Forwarder(self.resultLayout)

        request_ready = Signal()

        def FSMWBCycStart(request):  # noqa: N802
            # internal FSM function that starts Wishbone cycle
            m.d.sync += self.wbMaster.cyc.eq(1)
            m.d.sync += self.wbMaster.stb.eq(1)
            m.d.sync += self.wbMaster.adr.eq(request.addr)
            m.d.sync += self.wbMaster.dat_w.eq(Mux(request.we, request.data, 0))
            m.d.sync += self.wbMaster.we.eq(request.we)
            m.d.sync += self.wbMaster.sel.eq(request.sel)

        with m.FSM("Reset"):
            with m.State("Reset"):
                m.d.sync += self.wbMaster.rst.eq(1)
                m.next = "Idle"
            with m.State("Idle"):
                # default values for important signals
                m.d.sync += self.wbMaster.rst.eq(0)
                m.d.sync += self.wbMaster.stb.eq(0)
                m.d.sync += self.wbMaster.cyc.eq(0)
                m.d.comb += request_ready.eq(1)
                with m.If(self.request.run):
                    m.next = "WBWaitACK"

            with m.State("WBCycStart"):
                FSMWBCycStart(self.txn_req)
                m.next = "WBWaitACK"

            with m.State("WBWaitACK"):
                with m.If(self.wbMaster.ack | self.wbMaster.err):
                    m.d.comb += request_ready.eq(result.read.run)
                    with Transaction().body(m):
                        # will be always ready, as we checked that in Idle
                        result.write(m, data=Mux(self.txn_req.we, 0, self.wbMaster.dat_r), err=self.wbMaster.err)
                    with m.If(self.request.run):
                        m.next = "WBWaitACK"
                    with m.Else():
                        m.d.sync += self.wbMaster.cyc.eq(0)
                        m.d.sync += self.wbMaster.stb.eq(0)
                        m.next = "Idle"
                with m.If(self.wbMaster.rty):
                    m.d.sync += self.wbMaster.cyc.eq(1)
                    m.d.sync += self.wbMaster.stb.eq(0)
                    m.next = "WBCycStart"

        @def_method(m, self.result)
        def _():
            return result.read(m)

        @def_method(m, self.request, ready=request_ready & result.write.ready)
        def _(arg):
            m.d.sync += assign(self.txn_req, arg)
            # do WBCycStart state in the same clock cycle
            FSMWBCycStart(arg)

        result.write.schedule_before(self.request)
        result.read.schedule_before(self.request)

        return m


class PipelinedWishboneMaster(Elaboratable):
    """Pipelined Wishbone bus master interface.

    Parameters
    ----------
    wb_params: WishboneParameters
        Parameters for bus generation.
    max_req: int
        Size of the response buffer, limits the number of pending requests. Defaults to 8.

    Attributes
    ----------
    wb: Record (like WishboneLayout)
        Wishbone bus output.
    request: Method
        Transactional method to start a new Wishbone request.
        Ready if new request can be immediately sent.
        Takes `requestLayout` as argument.
    result: Method
        Transactional method to read results from completed requests sequentially.
        Ready if buffered results are available.
        Returns state of request (error or success) and data (in case of read request) as `resultLayout`.
    requests_finished: Signal, out
        True, if there are no requests waiting for response
    """

    def __init__(self, wb_params: WishboneParameters, *, max_req: int = 8):
        self.wb_params = wb_params
        self.max_req = max_req

        self.generate_method_layouts(wb_params)
        self.request = Method(i=self.request_in_layout)
        self.result = Method(o=self.result_out_layout)

        self.requests_finished = Signal()

        self.wb_layout = WishboneLayout(wb_params).wb_layout
        self.wb = Record(self.wb_layout)

    def generate_method_layouts(self, wb_params: WishboneParameters):
        # generate method layouts locally
        self.request_in_layout = [
            ("addr", wb_params.addr_width),
            ("data", wb_params.data_width),
            ("we", 1),
            ("sel", wb_params.data_width // wb_params.granularity),
        ]

        self.result_out_layout = [("data", wb_params.data_width), ("err", 1)]

    def elaborate(self, platform):
        m = TModule()

        m.submodules.result_fifo = self.result_fifo = BasicFifo(self.result_out_layout, self.max_req)
        m.submodules.result_write_adapter = self.result_write_adapter = AdapterTrans(self.result_fifo.write)

        pending_req_cnt = Signal(range(self.max_req + 1))
        req_start = Signal()
        req_finish = Signal()

        request_ready = Signal()
        # assure that responses to all instructions in flight can be buffered
        m.d.comb += request_ready.eq(~self.wb.stall & (pending_req_cnt + self.result_fifo.level < self.max_req))
        m.d.comb += self.requests_finished.eq(pending_req_cnt == 0)

        # assert cyc when starting new request or waiting for ack
        m.d.comb += self.wb.cyc.eq(self.wb.stb | pending_req_cnt > 0)

        with m.If(self.wb.ack | self.wb.err | self.wb.rty):
            m.d.comb += self.result_write_adapter.en.eq(1)
            m.d.comb += self.result_write_adapter.data_in.data.eq(self.wb.dat_r)
            # retrying in not possible in PipelinedMaster, treat RTY as ERR.
            m.d.comb += self.result_write_adapter.data_in.err.eq(self.wb.err | self.wb.rty)

            m.d.comb += req_finish.eq(1)

        self.result.proxy(m, self.result_fifo.read)

        @def_method(m, self.request, ready=request_ready)
        def _(arg) -> None:
            m.d.comb += self.wb.stb.eq(1)

            m.d.top_comb += [
                self.wb.adr.eq(arg.addr),
                self.wb.dat_w.eq(arg.data),
                self.wb.we.eq(arg.we),
                self.wb.sel.eq(arg.sel),
            ]

            m.d.comb += req_start.eq(1)

        with m.If(req_start & ~req_finish):
            m.d.sync += pending_req_cnt.eq(pending_req_cnt + 1)
        with m.If(req_finish & ~req_start):
            m.d.sync += pending_req_cnt.eq(pending_req_cnt - 1)

        return m


class WishboneMuxer(Elaboratable):
    """Wishbone Muxer.

    Connects one master to multiple slaves.

    Parameters
    ----------
    master_wb: Record (like WishboneLayout)
        Record of master inteface.
    slaves: List[Record]
        List of connected slaves' Wishbone Records (like WishboneLayout).
    ssel_tga: Signal
        Signal that selects the slave to connect. Signal width is the number of slaves and each bit coresponds
        to a slave. This signal is a Wishbone TGA (address tag), so it needs to be valid every time Wishbone STB
        is asserted.
        Note that if Pipelined Wishbone implementation is used, then before staring any new request with
        different `ssel_tga` value, all pending request have to be finished (and `stall` cleared) and
        there have to be  one cycle delay from previouse request (to deassert the STB signal).  Holding new
        requests should be implemented in block that controlls `ssel_tga` signal, before the Wishbone Master.
    """

    def __init__(self, master_wb: Record, slaves: List[Record], ssel_tga: Signal):
        self.master_wb = master_wb
        self.slaves = slaves
        self.sselTGA = ssel_tga

        select_bits = ssel_tga.shape().width
        assert select_bits == len(slaves)
        self.txn_sel = Signal(select_bits)
        self.txn_sel_r = Signal(select_bits)

        self.prev_stb = Signal()

    def elaborate(self, platform):
        m = TModule()

        m.d.sync += self.prev_stb.eq(self.master_wb.stb)

        # choose select signal directly from input on first cycle and latched one afterwards
        with m.If(self.master_wb.stb & ~self.prev_stb):
            m.d.sync += self.txn_sel_r.eq(self.sselTGA)
            m.d.comb += self.txn_sel.eq(self.sselTGA)
        with m.Else():
            m.d.comb += self.txn_sel.eq(self.txn_sel_r)

        for i in range(len(self.slaves)):
            # connect all M->S signals except stb
            m.d.comb += self.master_wb.connect(
                self.slaves[i],
                include=["dat_w", "rst", "cyc", "lock", "adr", "we", "sel"],
            )
            # use stb as select
            m.d.comb += self.slaves[i].stb.eq(self.txn_sel[i] & self.master_wb.stb)

        # bus termination signals S->M should be ORed
        m.d.comb += self.master_wb.ack.eq(reduce(operator.or_, [self.slaves[i].ack for i in range(len(self.slaves))]))
        m.d.comb += self.master_wb.err.eq(reduce(operator.or_, [self.slaves[i].err for i in range(len(self.slaves))]))
        m.d.comb += self.master_wb.rty.eq(reduce(operator.or_, [self.slaves[i].rty for i in range(len(self.slaves))]))
        for i in OneHotSwitchDynamic(m, self.txn_sel):
            # mux S->M data
            m.d.comb += self.master_wb.connect(self.slaves[i], include=["dat_r", "stall"])
        return m


# connects multiple masters to one slave
class WishboneArbiter(Elaboratable):
    """Wishbone Arbiter.

    Connects multiple masters to one slave.
    Bus is requested by asserting CYC signal and is granted to masters in a round robin manner.

    Parameters
    ----------
    slave_wb: Record (like WishboneLayout)
        Record of slave inteface.
    masters: List[Record]
        List of master interface Records.
    """

    def __init__(self, slave_wb: Record, masters: List[Record]):
        self.slave_wb = slave_wb
        self.masters = masters

        self.prev_cyc = Signal()
        # Amaranth round robin singals
        self.arb_enable = Signal()
        self.req_signal = Signal(len(masters))

    def elaborate(self, platform):
        m = TModule()

        m.d.sync += self.prev_cyc.eq(self.slave_wb.cyc)

        m.submodules.rr = rr = RoundRobin(count=len(self.masters))
        m.d.comb += [self.req_signal[i].eq(self.masters[i].cyc) for i in range(len(self.masters))]
        m.d.comb += rr.requests.eq(Mux(self.arb_enable, self.req_signal, 0))

        master_array = Array([master for master in self.masters])
        # If master ends wb cycle, enable rr input to select new master on next cycle if avaliable (cyc off for 1 cycle)
        # If selcted master is active, disable rr request input to preserve grant signal and correct rr state.
        # prev_cyc is used to select next master in new bus cycle, if previously selected master asserts cyc at the
        # same time as another one
        m.d.comb += self.arb_enable.eq((~master_array[m.submodules.rr.grant].cyc) | (~self.prev_cyc))

        for i in range(len(self.masters)):
            # mux S->M termination signals
            m.d.comb += self.masters[i].ack.eq((m.submodules.rr.grant == i) & self.slave_wb.ack)
            m.d.comb += self.masters[i].err.eq((m.submodules.rr.grant == i) & self.slave_wb.err)
            m.d.comb += self.masters[i].rty.eq((m.submodules.rr.grant == i) & self.slave_wb.rty)
            # remaining S->M signals are shared, master will only accept response if bus termination signal is present
            m.d.comb += self.masters[i].connect(self.slave_wb, include=["dat_r", "stall"])

        # combine reset singnal
        m.d.comb += self.slave_wb.rst.eq(reduce(operator.or_, [self.masters[i].rst for i in range(len(self.masters))]))

        # mux all M->S signals
        with m.Switch(m.submodules.rr.grant):
            for i in range(len(self.masters)):
                with m.Case(i):
                    m.d.comb += self.masters[i].connect(
                        self.slave_wb,
                        include=["dat_w", "cyc", "lock", "adr", "we", "sel", "stb"],
                    )

        # Disable slave when round robin is not valid at start of new request
        # This prevents chaning grant and muxes during Wishbone cycle
        with m.If((~m.submodules.rr.valid) & self.arb_enable):
            m.d.comb += self.slave_wb.stb.eq(0)

        return m


class WishboneMemorySlave(Elaboratable):
    """Wishbone slave with memory
    Wishbone slave interface with addressable memory underneath.

    Parameters
    ----------
    wb_params: WishboneParameters
        Parameters for bus generation.
    **kwargs: dict
        Keyword arguments for the underlying Amaranth's `Memory`. If `width` and `depth`
        are not specified, then they're inferred from `wb_params`: `data_width` becomes
        `width` and `2 ** addr_width` becomes `depth`.

    Attributes
    ----------
    bus: Record (like WishboneLayout)
        Wishbone bus record.
    """

    def __init__(self, wb_params: WishboneParameters, **kwargs):
        if "width" not in kwargs:
            kwargs["width"] = wb_params.data_width
        if kwargs["width"] not in (8, 16, 32, 64):
            raise RuntimeError("Memory width has to be one of: 8, 16, 32, 64")
        if "depth" not in kwargs:
            kwargs["depth"] = 2**wb_params.addr_width
        self.granularity = wb_params.granularity
        if self.granularity not in (8, 16, 32, 64):
            raise RuntimeError("Granularity has to be one of: 8, 16, 32, 64")

        self.mem = Memory(**kwargs)
        self.bus = Record(WishboneLayout(wb_params, master=False).wb_layout)

    def elaborate(self, platform):
        m = TModule()

        m.submodules.rdport = rdport = self.mem.read_port()
        m.submodules.wrport = wrport = self.mem.write_port(granularity=self.granularity)

        with m.FSM():
            with m.State("Start"):
                with m.If(self.bus.stb & self.bus.cyc):
                    with m.If(~self.bus.we):
                        with m.If(self.bus.adr < self.mem.depth):
                            m.d.comb += rdport.addr.eq(self.bus.adr)
                            # asserting rdport.en not required in case of a transparent port
                            m.next = "Read"
                        with m.Else():  # access outside bounds
                            m.d.comb += self.bus.err.eq(1)
                    with m.Else():
                        m.d.comb += wrport.addr.eq(self.bus.adr)
                        m.d.comb += wrport.en.eq(self.bus.sel)
                        m.d.comb += wrport.data.eq(self.bus.dat_w)
                        # writes can be ack'd earlier than reads because they don't return any data
                        m.d.comb += self.bus.ack.eq(1)

            with m.State("Read"):
                m.d.comb += self.bus.dat_r.eq(rdport.data)
                # ack can only be asserted when stb is asserted
                m.d.comb += self.bus.ack.eq(self.bus.stb)
                m.next = "Start"

        return m
