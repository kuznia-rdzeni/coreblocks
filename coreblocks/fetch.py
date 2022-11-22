from amaranth import Record, Module, Signal, Elaboratable
from .transactions import Method, Transaction
from .genparams import GenParams
from .layouts import FetchLayouts
from .wishbone import WishboneMaster


class Fetch(Elaboratable):
    def __init__(self, gen_params: GenParams, bus: WishboneMaster, cont: Method) -> None:
        """
        Simple fetch unit. It has a PC inside and increments it by `isa.ilen_bytes`
        after each fetch.

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

    def elaborate(self, platform) -> Module:
        m = Module()

        req = Record(self.bus.requestLayout)
        m.d.comb += req.addr.eq(self.pc >> 2)
        m.d.comb += req.sel.eq(2 ** (self.gp.isa.ilen // self.bus.wb_params.granularity) - 1)

        with Transaction().body(m):
            self.bus.request(m, req)

        with Transaction().body(m, request=(self.pc != self.halt_pc)):
            fetched = self.bus.result(m)

            with m.If(fetched.err == 0):

                out = Record(self.gp.get(FetchLayouts).raw_instr)

                m.d.comb += out.data.eq(fetched.data)

                m.d.sync += self.pc.eq(self.pc + self.gp.isa.ilen_bytes)
                self.cont(m, out)

        return m
