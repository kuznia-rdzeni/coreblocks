from amaranth import Record, Module, Signal, Elaboratable
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

    def elaborate(self, platform) -> Module:
        m = Module()
        pc = Signal(self.gp.isa.xlen)

        with Transaction().body(m):
            self.bus.request(m, {
                "addr": pc >> 2,
                "sel": 2 ** (self.gp.isa.ilen // self.bus.wb_params.granularity) - 1
            })

        with Transaction().body(m):
            fetched = self.bus.result(m)
            with m.If(fetched.err == 0):
                branch_detect = self.cont(m, {"data": fetched.data})
                # next wishbone request can't begin for the next 2 clock cycles
                # in current wishbone implementation so it's okay to update pc this way
                m.d.sync += pc.eq(branch_detect.next_pc)

        return m
