from amaranth import *
from amaranth.hdl.rec import DIR_FANIN, DIR_FANOUT
from amaranth.lib.scheduler import RoundRobin
from functools import reduce
from typing import List
import operator

from coreblocks.transactions import Method


class WishboneParameters:
    """Paramters of Wisbone bus
    Parameters
    ----------
    data_width: int
        Width of dat_r and dat_w Wishbone signals. Defaults to 64
    addr_width: int
        Width of adr Wishbone singal. Defaults to 64
    """

    def __init__(self, *, data_width=64, addr_width=64):
        self.data_width = data_width
        self.addr_width = addr_width


class WishboneLayout:
    """Wishbone bus Layout generator
    Parameters
    ----------
    wb_params: WishboneParameters
       Parameters used to generate Wisbone layout

    Attributes
    ----------
    wb_layout: Record
        Record of Wishbone bus
    """

    def __init__(self, wb_params: WishboneParameters):
        self.wb_layout = [
            ("dat_r", wb_params.data_width, DIR_FANIN),
            ("dat_w", wb_params.data_width, DIR_FANOUT),
            ("rst", 1, DIR_FANOUT),
            ("ack", 1, DIR_FANIN),
            ("adr", wb_params.addr_width, DIR_FANOUT),
            ("cyc", 1, DIR_FANOUT),
            ("err", 1, DIR_FANIN),
            ("lock", 1, DIR_FANOUT),
            ("rty", 1, DIR_FANIN),
            ("sel", 1, DIR_FANOUT),
            ("stb", 1, DIR_FANOUT),
            ("we", 1, DIR_FANOUT),
        ]


class WishboneMaster(Elaboratable):
    """Wishbone bus master interface.

    Paramters
    ---------
    wb_params: WishboneParameters
        Parameters for bus generation.

    Attributes
    ----------
    wbMaster: Record (like WishboneLayout)
        Wishbone bus output
    request: Method
        Transactional method to start a new Wishbone request.
        Ready when no request is being executed and previous result is read.
        Takes ```requestLayout``` as argument.
    result: Method
        Transactional method to read previous request result.
        Becomes ready after Wishbone request is completed.
        Returns state of request (error or success) and data (in case of read request) as ```resultLayout```.
    """

    def __init__(self, wb_params: WishboneParameters):
        self.wb_layout = WishboneLayout(wb_params).wb_layout
        self.wbMaster = Record(self.wb_layout)
        self.generate_layouts(wb_params)

        self.request = Method(i=self.requestLayout)
        self.result = Method(o=self.resultLayout)

        self.ready = Signal()
        self.res_ready = Signal()
        self.result_data = Record(self.resultLayout)

        # latched input signals
        self.txn_req = Record(self.requestLayout)

        self.ports = list(self.wbMaster.fields.values())

    def generate_layouts(self, wb_params: WishboneParameters):
        # generate method layouts locally
        self.requestLayout = [
            ("addr", wb_params.addr_width, DIR_FANIN),
            ("data", wb_params.data_width, DIR_FANIN),
            ("we", 1, DIR_FANIN),
        ]

        self.resultLayout = [("data", wb_params.data_width), ("err", 1)]

    def elaborate(self, platform):
        m = Module()

        def FSMWBCycStart(request):
            # internal FSM function that starts Wishbone cycle
            m.d.sync += self.wbMaster.cyc.eq(1)
            m.d.sync += self.wbMaster.stb.eq(1)
            m.d.sync += self.wbMaster.adr.eq(request.addr)
            m.d.sync += self.wbMaster.dat_w.eq(Mux(request.we, request.data, 0))
            m.d.sync += self.wbMaster.we.eq(request.we)
            m.next = "WBWaitACK"

        with self.result.body(m, ready=self.res_ready, out=self.result_data):
            m.d.sync += self.res_ready.eq(0)

        with m.FSM("Reset"):
            with m.State("Reset"):
                m.d.sync += self.wbMaster.rst.eq(1)
                m.next = "Idle"
            with m.State("Idle"):
                # default values for important signals
                m.d.sync += self.ready.eq(1)
                m.d.sync += self.wbMaster.rst.eq(0)
                m.d.sync += self.wbMaster.stb.eq(0)
                m.d.sync += self.wbMaster.cyc.eq(0)

                with self.request.body(m, ready=(self.ready & ~self.res_ready)) as request:
                    m.d.sync += self.ready.eq(0)
                    m.d.sync += self.txn_req.connect(request)
                    # do WBCycStart state in the same clock cycle
                    FSMWBCycStart(request)

            with m.State("WBCycStart"):
                FSMWBCycStart(self.txn_req)
                m.next = "WBWaitACK"

            with m.State("WBWaitACK"):
                with m.If(self.wbMaster.ack | self.wbMaster.err):
                    m.d.sync += self.wbMaster.cyc.eq(0)
                    m.d.sync += self.wbMaster.stb.eq(0)
                    m.d.sync += self.ready.eq(1)
                    m.d.sync += self.res_ready.eq(1)
                    m.d.sync += self.result_data.data.eq(Mux(self.txn_req.we, 0, self.wbMaster.dat_r))
                    m.d.sync += self.result_data.err.eq(self.wbMaster.err)
                    m.next = "Idle"
                with m.If(self.wbMaster.rty):
                    m.d.sync += self.wbMaster.cyc.eq(1)
                    m.d.sync += self.wbMaster.stb.eq(0)
                    m.next = "WBCycStart"

        return m


class WishboneMuxer(Elaboratable):
    """Wishbone Muxer
    Connects one master to multiple slaves.

    Paramters
    ---------
    masterWb: Record (like WishboneLayout)
        Record of master inteface.
    slaves: List[Record]
        List of connected slaves Wisbone Records (like WishboneLayout)
    sselTGA: Signal
        Signal that selects the slave to connect. Signal width is the number of slaves and each bit coresponds
        to a slave. This signal is a Wisnone TGA (address tag), so it needs to be valid every time Wisbone STB
        is asserted.
    """

    def __init__(self, masterWb: Record, slaves: List[Record], sselTGA: Signal):
        self.masterWb = masterWb
        self.slaves = slaves
        self.sselTGA = sselTGA

        selectBits = sselTGA.shape().width
        assert selectBits == len(slaves)
        self.txn_sel = Signal(selectBits)
        self.txn_sel_r = Signal(selectBits)

        self.prev_stb = Signal()

    def elaborate(self, platform):
        m = Module()

        m.d.sync += self.prev_stb.eq(self.masterWb.stb)

        # choose select signal directly from input on first cycle and latched one afterwards
        with m.If(self.masterWb.stb & ~self.prev_stb):
            m.d.sync += self.txn_sel_r.eq(self.sselTGA)
            m.d.comb += self.txn_sel.eq(self.sselTGA)
        with m.Else():
            m.d.comb += self.txn_sel.eq(self.txn_sel_r)

        for i in range(len(self.slaves)):
            # connect all M->S signals except stb
            m.d.comb += self.masterWb.connect(
                self.slaves[i],
                include=["dat_w", "rst", "cyc", "lock", "adr", "we", "sel"],
            )
            # use stb as select
            m.d.comb += self.slaves[i].stb.eq(self.txn_sel[i] & self.masterWb.stb)

        # bus termination signals S->M should be ORed
        m.d.comb += self.masterWb.ack.eq(reduce(operator.or_, [self.slaves[i].ack for i in range(len(self.slaves))]))
        m.d.comb += self.masterWb.err.eq(reduce(operator.or_, [self.slaves[i].err for i in range(len(self.slaves))]))
        m.d.comb += self.masterWb.rty.eq(reduce(operator.or_, [self.slaves[i].rty for i in range(len(self.slaves))]))
        with m.Switch(self.txn_sel):
            for i in range(len(self.slaves)):
                with m.Case(("-" * (len(self.slaves) - i - 1)) + "1" + ("-" * i)):
                    # mux S->M data
                    m.d.comb += self.masterWb.connect(self.slaves[i], include=["dat_r"])
        return m


# connects multiple masters to one slave
class WishboneArbiter(Elaboratable):
    """Wishbone Arbiter
    Connects multiple masters to one slave.
    Bus is requested by asserting CYC signal and is granted to masters in a round robin manner.

    Paramters
    ---------
    slaveWb: Record (like WishboneLayout)
        Record of slave inteface.
    masters: List[Record]
        List of master interface Records.
    """

    def __init__(self, slaveWb: Record, masters: List[Record]):
        self.slaveWb = slaveWb
        self.masters = masters

        self.prev_cyc = Signal()
        # Amaranth round robin singals
        self.arb_enable = Signal()
        self.req_signal = Signal(len(masters))

    def elaborate(self, plaform):
        m = Module()

        m.d.sync += self.prev_cyc.eq(self.slaveWb.cyc)

        m.submodules.rr = RoundRobin(count=len(self.masters))
        m.d.comb += [self.req_signal[i].eq(self.masters[i].cyc) for i in range(len(self.masters))]
        m.d.comb += m.submodules.rr.requests.eq(Mux(self.arb_enable, self.req_signal, 0))

        masterArray = Array([master for master in self.masters])
        # If master ends wb cycle, enable rr input to select new master on next cycle if avaliable (cyc off for 1 cycle)
        # If selcted master is active, disable rr request input to preserve grant signal and correct rr state.
        # prev_cyc is used to select next master in new bus cycle, if previously selected master asserts cyc at the
        # same time as another one
        m.d.comb += self.arb_enable.eq((~masterArray[m.submodules.rr.grant].cyc) | (~self.prev_cyc))

        for i in range(len(self.masters)):
            # mux S->M termination signals
            m.d.comb += self.masters[i].ack.eq((m.submodules.rr.grant == i) & self.slaveWb.ack)
            m.d.comb += self.masters[i].err.eq((m.submodules.rr.grant == i) & self.slaveWb.err)
            m.d.comb += self.masters[i].rty.eq((m.submodules.rr.grant == i) & self.slaveWb.rty)
            # remaining S->M signals are shared, master will only accept response if bus termination signal is present
            m.d.comb += self.masters[i].dat_r.eq(self.slaveWb.dat_r)

        # combine reset singnal
        m.d.comb += self.slaveWb.rst.eq(reduce(operator.or_, [self.masters[i].rst for i in range(len(self.masters))]))

        # mux all M->S signals
        with m.Switch(m.submodules.rr.grant):
            for i in range(len(self.masters)):
                with m.Case(i):
                    m.d.comb += self.masters[i].connect(
                        self.slaveWb,
                        include=["dat_w", "cyc", "lock", "adr", "we", "sel", "stb"],
                    )

        # Disable slave when round robin is not valid at start of new request
        # This prevents chaning grant and muxes during Wishbone cycle
        with m.If((~m.submodules.rr.valid) & self.arb_enable):
            m.d.comb += self.slaveWb.stb.eq(0)

        return m
