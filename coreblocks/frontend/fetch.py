from amaranth import *
from coreblocks.utils.fifo import BasicFifo
from coreblocks.frontend.icache import ICacheInterface
from ..transactions import def_method, Method, Transaction, TModule
from ..params import GenParams, FetchLayouts, DependencyManager, VerifyBranchKey


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

        # no early_verify_branch for now, will be needed to prevent flushing
        # predictions on fence.i
        fetch_layouts = self.gp.get(FetchLayouts)
        self.verify_branch = Method(i=fetch_layouts.branch_verify_in, o=fetch_layouts.branch_verify_out)

        connections = self.gp.get(DependencyManager)
        connections.add_dependency(VerifyBranchKey(), self.verify_branch)

        # PC of the last fetched instruction. For now only used in tests.
        self.pc = Signal(self.gp.isa.xlen)

    def use_side_fx(self, enable_side_fx: Value):
        self.enable_side_fx = enable_side_fx

    def predict_next_pc(self, m, pc):
        """
        The simplest predictor possible.  95%+ accuracy in real-life applications.
        """
        return pc + self.gp.isa.ilen_bytes

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

            m.d.sync += speculative_pc.eq(self.predict_next_pc(m, speculative_pc))

        def stall():
            m.d.sync += stalled.eq(1)
            with m.If(~stalled):
                # if the fetcher is stalled, the spin bit has already been flipped
                m.d.sync += spin.eq(~spin)

        with Transaction().body(m):
            target = self.fetch_target_queue.read(m)
            res = self.icache.accept_res(m)

            with m.If(spin == target.spin):
                instr = Signal(self.gp.isa.ilen)

                with m.If(res.error):
                    # TODO: this should ideally bypass decoder and push a decoded 'trigger ibus
                    # error' instruction instead.  For now push UNIMP, which happens to be 0x0000
                    # in RV32C, and should throw 'illegal instruction' exception.
                    # If we do not support C, it should throw the same exception anyway.
                    m.d.comb += instr.eq(0x0000)
                    stall()

                with m.Else():
                    m.d.sync += self.pc.eq(target.addr)
                    m.d.comb += instr.eq(res.instr)

                self.cont(m, data=instr, pc=target.addr)

        self.sfx_disabled = sfx_disabled = Signal()
        with m.If(~self.enable_side_fx):  # if sfx are disabled
            stall()
            m.d.sync += sfx_disabled.eq(1)

        with m.If(sfx_disabled & self.enable_side_fx):  # if sfx switched to enabled
            m.d.sync += stalled.eq(0)
            m.d.sync += sfx_disabled.eq(0)

        @def_method(m, self.verify_branch)
        def _(from_pc: Value, next_pc: Value):
            '''TODO: also compare rob_id to ensure correct order'''
            mispredict = Signal()

            with m.If(self.enable_side_fx):
                # this might not work if we dropped the prediction,
                # therefore we should maintain LRU or change attitude
                predicted_next_pc = self.predict_next_pc(m, from_pc)

                # here we could feed feedback to predictor

                with m.If(predicted_next_pc != next_pc):
                    m.d.sync += speculative_pc.eq(next_pc)
                    m.d.comb += mispredict.eq(1)
                    stall()

            return {"mispredict": mispredict}

        return m
