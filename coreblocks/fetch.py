from amaranth import Record, Module, Signal, Elaboratable
from .transactions import Method, Transaction
from .genparams import GenParams
from .layouts import FetchLayouts
from .wishbone import WishboneMaster


class Fetch(Elaboratable):
    def __init__(self, gen_params: GenParams, bus: WishboneMaster, cont: Method) -> None:
        self.gp = gen_params
        self.bus = bus
        self.cont = cont

        self.pc = Signal(bus.wb_params.addr_width, reset=gen_params.start_pc)

    def elaborate(self, platform) -> Module:
        m = Module()

        req = Record(self.bus.requestLayout)
        m.d.comb += req.addr.eq(self.pc)

        with Transaction().body(m):
            self.bus.request(m, req)

        with Transaction().body(m):
            fetched = self.bus.result(m)

            with m.If(fetched.err == 0):

                out = Record(self.gp.get(FetchLayouts).raw_instr)

                m.d.comb += out.data.eq(fetched.data)

                m.d.sync += self.pc.eq(self.pc + self.gp.isa.ilen_bytes)
                self.cont(m, out)

        return m
