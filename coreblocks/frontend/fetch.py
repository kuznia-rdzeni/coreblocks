from amaranth import *
from coreblocks.transactions.core import def_method
from coreblocks.utils.fifo import BasicFifo
from coreblocks.frontend.icache import ICache, SimpleWBCacheRefiller
from ..transactions import Method, Transaction
from ..params import GenParams, FetchLayouts, ICacheLayouts
from ..peripherals.wishbone import WishboneMaster


class Fetch(Elaboratable):
    """
    Simple fetch unit. It has a PC inside and increments it by `isa.ilen_bytes`
    after each fetch.
    """

    def __init__(self, gen_params: GenParams, cache_req: Method, cache_resp: Method, cont: Method) -> None:
        """
        Parameters
        ----------
        gen_params : GenParams
            Instance of GenParams with parameters which should be used to generate
            fetch unit.
        cont : Method
            Method which should be invoked to send fetched data to the next step.
            It has layout as described by `FetchLayout`.
        """
        self.gp = gen_params
        self.cache_req = cache_req
        self.cache_resp = cache_resp
        self.cont = cont

        self.pc = Signal(gen_params.isa.xlen, reset=gen_params.start_pc)
        #self.halt_pc = Signal(bus.wb_params.addr_width, reset=2**bus.wb_params.addr_width - 1)

        self.verify_branch = Method(i=self.gp.get(FetchLayouts).branch_verify)

    def elaborate(self, platform) -> Module:
        m = Module()

        m.submodules.fetch_target_queue = self.fetch_target_queue = BasicFifo(layout=[("addr", self.gp.isa.xlen)], depth=2)

        speculative_pc = Signal(self.gp.isa.xlen, reset=self.gp.start_pc)
        
        discard_next = Signal()
        stalled = Signal()

        with Transaction().body(m, request=~stalled):
            self.cache_req(m, addr=speculative_pc)
            self.fetch_target_queue.write(m, addr=speculative_pc)

            m.d.sync += speculative_pc.eq(speculative_pc + self.gp.isa.ilen_bytes)

        with Transaction().body(m):
            pc = self.fetch_target_queue.read(m).addr   
            res = self.cache_resp(m)

            # TODO: find a better way to fail when there's a fetch error.
            instr = Mux(res.error, 0, res.instr)

            # bits 4:7 currently are enough to uniquely distinguish jumps and branches,
            # but this could potentially change in the future since there's a reserved
            # (currently unused) bit pattern in the spec, see table 19.1 in RISC-V spec v2.2
            is_branch = instr[4:7] == 0b110

            with m.If(discard_next):
                m.d.sync += discard_next.eq(0)
            with m.Else():
                with m.If(is_branch):
                    m.d.sync += stalled.eq(1)
                    m.d.sync += discard_next.eq(1)

                self.cont(m, data=instr, pc=pc)


        @def_method(m, self.verify_branch, ready=stalled)
        def _(next_pc: Value):
            m.d.sync += speculative_pc.eq(next_pc)
            m.d.sync += stalled.eq(0)

        return m
