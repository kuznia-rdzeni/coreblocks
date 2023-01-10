from amaranth import Record, Module, Signal, Elaboratable
from coreblocks.transactions.core import def_method
from ..transactions import Method, Transaction
from ..params import GenParams, FetchLayouts
from ..peripherals.wishbone import WishboneMaster


class Fetch(Elaboratable):
    """
    Simple fetch unit. It has a PC inside and increments it by `isa.ilen_bytes`
    after each fetch.
    """

    def __init__(self, gen_params: GenParams, bus: WishboneMaster, cont: Method) -> None:
        """
        Parameters
        ----------
        gen_params : GenParams
            Instance of GenParams with parameters which should be used to generate
            fetch unit.
        bus : WishboneMaster
            Instance of WishboneMaster connected to memory with instructions
            to be executed by the core.
        cont : Method
            Method which should be invoked to send fetched data to the next step.
            It has layout as described by `FetchLayout`.
        """
        self.gp = gen_params
        self.bus = bus
        self.cont = cont

        self.pc = Signal(bus.wb_params.addr_width, reset=gen_params.start_pc)
        self.halt_pc = Signal(bus.wb_params.addr_width, reset=2**bus.wb_params.addr_width - 1)

        self.verify_branch = Method(i=self.gp.get(FetchLayouts).branch_verify)

    def elaborate(self, platform) -> Module:
        m = Module()

        stalled = Signal()
        req = Record(self.bus.requestLayout)
        m.d.comb += req.addr.eq(self.pc >> 2)
        m.d.comb += req.sel.eq(2 ** (self.gp.isa.ilen // self.bus.wb_params.granularity) - 1)

        with Transaction().body(m, request=(~stalled)):
            self.bus.request(m, req)

        with Transaction().body(m, request=(self.pc != self.halt_pc)):
            fetched = self.bus.result(m)

            with m.If(fetched.err == 0):
                # bits 4:7 currently are enough to uniquely distinguish jumps and branches,
                # but this could potentially change in the future since there's a reserved
                # (currently unused) bit pattern in the spec, see table 19.1 in RISC-V spec v2.2
                is_branch = fetched.data[4:7] == 0b110
                with m.If(is_branch):
                    m.d.sync += stalled.eq(1)

                m.d.sync += self.pc.eq(self.pc + self.gp.isa.ilen_bytes)

                self.cont(m, {"data": fetched.data, "pc": self.pc})

        @def_method(m, self.verify_branch, ready=stalled)
        def _(arg):
            m.d.sync += self.pc.eq(arg.next_pc)
            m.d.sync += stalled.eq(0)

        return m
