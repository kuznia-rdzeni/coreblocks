from amaranth import Array, Record, Module, Signal, Elaboratable
from .transactions import Method, def_method, Transaction
from .genparams import GenParams
from .layouts import ROBLayouts
from .wishbone import WishboneMaster


class Fetch(Elaboratable):
    def __init__(self, gen_params: GenParams, bus: WishboneMaster, cont: Method) -> None:
        self.gp = gen_params
        self.bus = bus
        self.cont = cont

        self.pc = Signal(bus.wb_params.addr_width)

    def elaborate(self, platform) -> Module:
        m = Module()

        req = Record(self.bus.requestLayout)
        m.d.comb += req.addr.eq(self.pc)
        m.d.comb += req.data.eq(0)
        m.d.comb += req.we.eq(0)

        with Transaction().body(m):
            self.bus.request(m, req)

        with Transaction().body(m):
            fetched = self.bus.result(m)

            with m.If(fetched.err == 0):
                m.d.sync += self.pc.eq(self.pc + (self.gp.isa.ilen // 8))
                self.cont(m, fetched)

        return m
