from amaranth import *
from amaranth.hdl.rec import DIR_FANIN, DIR_FANOUT
from amaranth.lib.scheduler import RoundRobin
from functools import reduce
import operator

from coreblocks.transactions import Method

wbRecord = Record([
            ("dat_r", 64, DIR_FANIN),
            ("dat_w", 64, DIR_FANOUT),
            ("rst", 1, DIR_FANOUT),
            ("ack", 1, DIR_FANIN),
            ("adr", 64, DIR_FANOUT),
            ("cyc", 1, DIR_FANOUT),
            ("err", 1, DIR_FANIN),
            ("lock", 1, DIR_FANOUT),
            ("rty", 1, DIR_FANIN), 
            ("sel", 1, DIR_FANOUT),
            ("stb", 1, DIR_FANOUT),
            ("we", 1, DIR_FANOUT)])

# Simple cpu to Wishbone master interface
class WishboneMaster(Elaboratable):
    requestLayout = [
        ("addr", wbRecord.adr.shape().width, DIR_FANIN),
        ("data", wbRecord.dat_w.shape().width, DIR_FANIN),
        ("we", 1, DIR_FANIN),
    ]

    resultLayout = [
        ("data", wbRecord.dat_r.shape().width),
        ("err", 1)
    ]

    # WishboneMaster.wbMaster is WB bus output (as wbRecord)
    # 
    # Methods avaliable to CPU:
    # .request - Method that starts new Wishbone request. Ready when no request is currently executed. Takes requestLayout as argument.
    # .result  - Method that becomes ready when Wishbone request finishes. Returns state of request (error or success) and data (in case of read request) as resultLayout.
    def __init__(self):
        self.wbMaster = Record.like(wbRecord)

        self.request = Method(i=self.requestLayout)
        self.result = Method(o=self.resultLayout)

        self.ready = Signal()
        self.res_ready = Signal()
        self.result_data = Record(self.resultLayout)

        # latched input signals
        self.txn_req = Record(self.requestLayout)

        self.ports = list(self.wbMaster.fields.values())

    def elaborate(self, platform):
        m = Module()
        
        def FSMWBCycStart(request):
            m.d.sync += self.wbMaster.cyc.eq(1)
            m.d.sync += self.wbMaster.stb.eq(1)
            m.d.sync += self.wbMaster.adr.eq(request.addr)
            m.d.sync += self.wbMaster.dat_w.eq(Mux(request.we, request.data, 0))
            m.d.sync += self.wbMaster.we.eq(request.we)
            m.next = "WBWaitACK" 
        
        with self.result.body(m, ready=self.res_ready, out=self.result_data):
            m.d.sync += self.res_ready.eq(0)

        with m.FSM("Reset") as fsm:
            with m.State("Reset"): 
                m.d.sync += self.wbMaster.rst.eq(1)
                m.next = "Idle"
            with m.State("Idle"):
                # default values for important signals
                m.d.sync += self.ready.eq(1)
                m.d.sync += self.wbMaster.rst.eq(0)
                m.d.sync += self.wbMaster.stb.eq(0)
                m.d.sync += self.wbMaster.cyc.eq(0)

                with self.request.body(m, ready=(self.ready & ~self.res_ready)):
                    m.d.sync += self.ready.eq(0)
                    m.d.sync += self.txn_req.connect(self.request.data_in)
                    # do WBCycStart state in the same clock cycle
                    FSMWBCycStart(self.request.data_in)
             
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

# connects one master to multiple slaves
class WishboneMuxer(Elaboratable):
    # masterWb - wbRecord of  master interface, slaves - list of slave wbRecords, sselTGA - slave select signal
    # set sselTGA (wishbone address tag) every time when asserting wishbone STB, to select destionation interface
    def __init__(self, masterWb, slaves, sselTGA):
        self.masterWb = masterWb
        self.slaves = slaves
        self.sselTGA = sselTGA

        selectBits = sselTGA.shape().width
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
            m.d.comb += self.masterWb.connect(self.slaves[i], include=["dat_w", "rst", "cyc", "lock", "adr", "we", "sel"])
            # use stb as select
            m.d.comb += self.slaves[i].stb.eq((self.txn_sel == i) & self.masterWb.stb)
        
        # bus termination signals S->M should be ORed
        m.d.comb += self.masterWb.ack.eq(reduce(operator.or_, [self.slaves[i].ack for i in range(len(self.slaves))]))
        m.d.comb += self.masterWb.err.eq(reduce(operator.or_, [self.slaves[i].err for i in range(len(self.slaves))]))
        m.d.comb += self.masterWb.rty.eq(reduce(operator.or_, [self.slaves[i].rty for i in range(len(self.slaves))]))
        with m.Switch(self.txn_sel):
            for i in range(len(self.slaves)):
                with m.Case(i):
                    # mux S->M data
                    m.d.comb += self.masterWb.connect(self.slaves[i], include=["dat_r"])
        return m

# connects multiple masters to one slave
class WishboneArbiter(Elaboratable):
    # slaveWb - wbRecord of slave interface, masters - list of wbRecords for master interfaces
    def __init__(self, slaveWb, masters):
        self.slaveWb = slaveWb
        self.masters = masters

        self.prev_cyc  = Signal()
        # Amaranth round robin singals
        self.arb_enable = Signal()
        self.req_signal = Signal(len(masters))
    def elaborate(self, plaform):
        m = Module()

        m.submodules.rr = RoundRobin(count=len(self.masters))    
        m.d.comb += [self.req_signal[i].eq(self.masters[i].cyc) for i in range(len(self.masters))]
        m.d.comb += m.submodules.rr.requests.eq(Mux(self.arb_enable, self.req_signal, 0))
        
        m.d.sync += self.prev_cyc.eq(self.slaveWb.cyc)

        for i in range(len(self.masters)):
            # mux S->M termination signals
            m.d.comb += self.masters[i].ack.eq((m.submodules.rr.grant == i) & self.slaveWb.ack)
            m.d.comb += self.masters[i].err.eq((m.submodules.rr.grant == i) & self.slaveWb.err)
            m.d.comb += self.masters[i].rty.eq((m.submodules.rr.grant == i) & self.slaveWb.rty)
            # remaining S->M signals are shared, master will only accept response if bus termination signal is present
            m.d.comb += self.slaveWb.connect(self.masters[i], include=["dat_r"])

        # combine reset singnal
        m.d.comb += self.slaveWb.rst.eq(reduce(operator.or_, [self.masters[i].rst for i in range(len(self.masters))]))
        
        # mux all M->S signals
        with m.Switch(m.submodules.rr.grant):
            for i in range(len(self.masters)):
                with m.Case(i):
                    m.d.comb += self.masters[i].connect(self.slaveWb, include=["dat_w", "cyc", "lock", "adr", "we", "sel", "stb"])
        
        masterArray = Array([master for master in self.masters])
        # If master ends wb cycle, enable rr input to select new master on next cycle if avaliable (1 cycle break in cyc)
        # If selcted master is active, disable rr request input to preserve grant signal and correct rr state.
        # prev_cyc is used to select next master in new bus cycle, if previously selected master asserts cyc at the same time as another one
        m.d.comb += self.arb_enable.eq((~masterArray[m.submodules.rr.grant].cyc) | (~self.prev_cyc))
        
        return m  
