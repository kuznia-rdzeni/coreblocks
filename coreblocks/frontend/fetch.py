from amaranth import *
from coreblocks.transactions.core import def_method
from coreblocks.utils.fifo import BasicFifo
from ..transactions import Method, Transaction
from ..params import GenParams, FetchLayouts


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
        cache_req : Method
            Method that is used to issue a request to the instruction cache.
            It has layout ICacheLayouts::issue_req.
        cache_resp : Method
            Method that is used to accept the response from the instruction cache.
            It has layout ICacheLayouts::accept_resp.
        cont : Method
            Method which should be invoked to send fetched data to the next step.
            It has layout as described by `FetchLayout`.
        """
        self.gp = gen_params
        self.cache_req = cache_req
        self.cache_resp = cache_resp
        self.cont = cont

        self.verify_branch = Method(i=self.gp.get(FetchLayouts).branch_verify)

        # Signals used for debugging purposes
        self.halt_pc = Signal(self.gp.isa.xlen, reset=2**self.gp.isa.xlen - 1)
        self.pc = Signal(self.gp.isa.xlen)

    def elaborate(self, platform) -> Module:
        m = Module()

        m.submodules.fetch_target_queue = self.fetch_target_queue = BasicFifo(
            layout=[("addr", self.gp.isa.xlen)], depth=2
        )

        speculative_pc = Signal(self.gp.isa.xlen, reset=self.gp.start_pc)

        discard_next = Signal()
        stalled = Signal()

        with Transaction().body(m, request=~stalled):
            self.cache_req(m, addr=speculative_pc)
            self.fetch_target_queue.write(m, addr=speculative_pc)

            m.d.sync += speculative_pc.eq(speculative_pc + self.gp.isa.ilen_bytes)

        with Transaction().body(m, request=(self.pc != self.halt_pc)):
            pc = self.fetch_target_queue.read(m).addr
            res = self.cache_resp(m)

            # bits 4:7 currently are enough to uniquely distinguish jumps and branches,
            # but this could potentially change in the future since there's a reserved
            # (currently unused) bit pattern in the spec, see table 19.1 in RISC-V spec v2.2
            is_branch = res.instr[4:7] == 0b110

            with m.If(discard_next):
                m.d.sync += discard_next.eq(0)

            # TODO: find a better way to fail when there's a fetch error.
            with m.Elif(res.error == 0):
                with m.If(is_branch):
                    m.d.sync += stalled.eq(1)
                    m.d.sync += discard_next.eq(1)

                m.d.sync += self.pc.eq(pc)

                self.cont(m, data=res.instr, pc=pc)

        @def_method(m, self.verify_branch, ready=stalled)
        def _(next_pc: Value):
            m.d.sync += speculative_pc.eq(next_pc)
            m.d.sync += stalled.eq(0)

        return m
