from amaranth import *
from coreblocks.utils.fifo import BasicFifo
from coreblocks.frontend.icache import ICacheInterface
from ..transactions import def_method, Method, Transaction, TModule
from ..params import GenParams, FetchLayouts


class Fetch(Elaboratable):
    """
    Simple fetch unit. It has a PC inside and increments it by `isa.ilen_bytes`
    after each fetch.
    """

    def __init__(self, gen_params: GenParams, icache: ICacheInterface, cont: Method) -> None:
        """
        Parameters
        ----------
        gen_params : GenParams
            Instance of GenParams with parameters which should be used to generate
            fetch unit.
        icache : ICacheInterface
            Instruction Cache
        cont : Method
            Method which should be invoked to send fetched data to the next step.
            It has layout as described by `FetchLayout`.
        """
        self.gp = gen_params
        self.icache = icache
        self.cont = cont

        layouts = self.gp.get(FetchLayouts)
        self.verify_branch = Method(i=layouts.branch_verify_in, o=layouts.branch_verify_out)
        self.stall = Method()

        # PC of the last fetched instruction. For now only used in tests.
        self.pc = Signal(self.gp.isa.xlen)

    def elaborate(self, platform):
        m = TModule()

        m.submodules.fetch_target_queue = self.fetch_target_queue = BasicFifo(
            layout=[("addr", self.gp.isa.xlen), ("spin", 1)], depth=2
        )

        speculative_pc = Signal(self.gp.isa.xlen, reset=self.gp.start_pc)

        stalled = Signal()
        spin = Signal()

        with Transaction().body(m, request=~stalled):
            self.icache.issue_req(m, addr=speculative_pc)
            self.fetch_target_queue.write(m, addr=speculative_pc, spin=spin)

            m.d.sync += speculative_pc.eq(speculative_pc + self.gp.isa.ilen_bytes)

        def stall():
            m.d.sync += stalled.eq(1)
            with m.If(~stalled):
                m.d.sync += spin.eq(~spin)

        with Transaction().body(m):
            target = self.fetch_target_queue.read(m)
            res = self.icache.accept_res(m)

            # bits 4:7 currently are enough to uniquely distinguish jumps and branches,
            # but this could potentially change in the future since there's a reserved
            # (currently unused) bit pattern in the spec, see table 19.1 in RISC-V spec v2.2
            is_branch = res.instr[4:7] == 0b110
            is_system = res.instr[2:7] == 0b11100

            with m.If(spin == target.spin):
                instr = Signal(self.gp.isa.ilen)

                with m.If(res.error != 0):
                    # TODO: this should ideally bypass decoder and push a decoded 'trigger ibus
                    # error' instruction instead.  For now push UNIMP, which happens to be 0x0000
                    # in RV32C, and should throw 'illegal instruction' exception.
                    # If we do not support C, it should throw the same exception anyway.
                    m.d.comb += instr.eq(0x0000)

                with m.Else():
                    with m.If(is_branch | is_system):
                        stall()

                    m.d.sync += self.pc.eq(target.addr)
                    m.d.comb += instr.eq(res.instr)

                self.cont(m, data=instr, pc=target.addr)

        self.verify_branch.add_conflict(self.stall)

        @def_method(m, self.stall)
        def _():
            m.d.sync += stalled.eq(1)

        @def_method(m, self.verify_branch, ready=stalled)
        def _(from_pc: Value, next_pc: Value):
            m.d.sync += speculative_pc.eq(next_pc)
            m.d.sync += stalled.eq(0)
            return self.pc

        return m
