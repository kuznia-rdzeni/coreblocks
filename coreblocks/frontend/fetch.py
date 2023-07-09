from amaranth import *
from coreblocks.utils.fifo import BasicFifo, Semaphore
from coreblocks.frontend.icache import ICacheInterface
from coreblocks.frontend.rvc import InstrDecompress, is_instr_compressed
from transactron import def_method, Method, Transaction, TModule
from ..params import *


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
            layout=[("addr", self.gp.isa.xlen), ("tag", 1)], depth=2
        )

        speculative_pc = Signal(self.gp.isa.xlen, reset=self.gp.start_pc)

        stalled = Signal()
        tag = Signal(1)
        request_trans = Transaction(name="request")
        response_trans = Transaction(name="response")

        with request_trans.body(m, request=~stalled):
            self.icache.issue_req(m, addr=speculative_pc)
            self.fetch_target_queue.write(m, addr=speculative_pc, tag=tag)

            m.d.sync += speculative_pc.eq(speculative_pc + self.gp.isa.ilen_bytes)

        def stall():
            m.d.sync += stalled.eq(1)
            with m.If(~stalled):
                m.d.sync += tag.eq(tag + 1)

        with response_trans.body(m):
            target = self.fetch_target_queue.read(m)
            res = self.icache.accept_res(m)

            opcode = res.instr[2:7]
            # whether we have to wait for the retirement of this instruction before we make futher speculation
            unsafe_instr = (
                (opcode == Opcode.BRANCH) | (opcode == Opcode.JAL) | (opcode == Opcode.JALR) | (opcode == Opcode.SYSTEM)
            )

            with m.If(tag == target.tag):
                instr = Signal(self.gp.isa.ilen)
                fetch_error = Signal()

                with m.If(res.error):
                    # TODO: Raise different code for page fault when supported
                    stall()
                    m.d.comb += fetch_error.eq(1)
                with m.Else():
                    with m.If(unsafe_instr):
                        stall()
                    m.d.sync += self.pc.eq(target.addr)
                    m.d.comb += instr.eq(res.instr)

                self.cont(m, data=instr, pc=target.addr, access_fault=fetch_error, rvc=0)

        self.verify_branch.add_conflict(self.stall)

        # These aren't strictly necessary as verify_branch being defined later
        # in the code will take precedence when setting speculative_pc, stalled
        # and tag, but you can uncomment these for a fun debugging session:
        # from ..transactions import Priority
        # self.verify_branch.add_conflict(response_trans, priority=Priority.LEFT)
        # self.verify_branch.add_conflict(request_trans, priority=Priority.LEFT)

        @def_method(m, self.stall)
        def _():
            stall()

        @def_method(m, self.verify_branch)
        def _(from_pc: Value, next_pc: Value):
            m.d.sync += speculative_pc.eq(next_pc)
            m.d.sync += stalled.eq(0)
            return self.pc

        return m


class UnalignedFetch(Elaboratable):
    """
    Simple fetch unit that works with unaligned and RVC instructions.
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

    def elaborate(self, platform) -> TModule:
        m = TModule()

        m.submodules.req_limiter = req_limiter = Semaphore(2)

        m.submodules.decompress = decompress = InstrDecompress(self.gp)

        cache_req_pc = Signal(self.gp.isa.xlen, reset=self.gp.start_pc)
        current_pc = Signal(self.gp.isa.xlen, reset=self.gp.start_pc)

        flushing = Signal()
        stalled = Signal()

        with Transaction().body(m, request=~stalled):
            aligned_pc = Cat(Repl(0, 2), cache_req_pc[2:])
            self.icache.issue_req(m, addr=aligned_pc)
            req_limiter.acquire(m)

            m.d.sync += cache_req_pc.eq(cache_req_pc + 4)

        with m.If(req_limiter.count == 0):
            m.d.sync += flushing.eq(0)

        half_instr_buff = Signal(16)
        half_instr_buff_v = Signal()

        with Transaction().body(m):
            fetching_now = Signal()
            m.d.top_comb += fetching_now.eq(~(half_instr_buff_v & is_instr_compressed(half_instr_buff)))
            with m.If(fetching_now):
                cache_resp = self.icache.accept_res(m)
                req_limiter.release(m)

            is_unaligned = current_pc[1]
            resp_upper_half = cache_resp.instr[16:]
            resp_lower_half = cache_resp.instr[:16]
            resp_first_half = Mux(is_unaligned, resp_upper_half, resp_lower_half)
            resp_valid = ~flushing & (cache_resp.error == 0)
            is_resp_upper_rvc = Signal()
            m.d.top_comb += is_resp_upper_rvc.eq(is_instr_compressed(resp_upper_half))

            instr_lo_half = Signal(16)
            m.d.top_comb += instr_lo_half.eq(Mux(half_instr_buff_v, half_instr_buff, resp_first_half))
            m.d.top_comb += decompress.instr_in.eq(instr_lo_half)

            is_rvc = is_instr_compressed(instr_lo_half)

            full_instr = Mux(half_instr_buff_v, Cat(half_instr_buff, resp_lower_half), cache_resp.instr)

            instr = Signal(32)
            m.d.top_comb += instr.eq(Mux(is_rvc, decompress.instr_out, full_instr))

            opcode = instr[2:7]
            # whether we have to wait for the retirement of this instruction before we make futher speculation
            unsafe_instr = (
                (opcode == Opcode.BRANCH) | (opcode == Opcode.JAL) | (opcode == Opcode.JALR) | (opcode == Opcode.SYSTEM)
            )

            # Check if we are ready to dispatch an instruction in the current cycle.
            # This can happen in three situations:
            # - we have a half of the instruction in the buffer, so either it is a compressed
            #   instruction or we have just fetched another half,
            # - the instruction is aligned, so we fetched the whole,
            # - the instruction is unaligned, but it is a compressed instruction.
            ready_to_dispatch = half_instr_buff_v | ~is_unaligned | is_resp_upper_rvc

            # We have to store the upper half of the response if the current
            # response from the cache is valid and either:
            # - we fetched the first half of an unaligned instruction and it is not compressed,
            # - we fetched an aligned instruction, but the lower half is compressed,
            # - we have already something in the buffer (meaning that now we are completing the previous instruction).
            m.d.sync += half_instr_buff_v.eq(
                resp_valid
                & fetching_now
                & (
                    (is_unaligned & ~is_resp_upper_rvc)
                    | (~is_unaligned & is_instr_compressed(resp_lower_half))
                    | half_instr_buff_v
                )
            )
            m.d.sync += half_instr_buff.eq(resp_upper_half)

            with m.If((resp_valid & ready_to_dispatch) | (cache_resp.error & ~stalled)):
                with m.If(unsafe_instr | cache_resp.error):
                    m.d.sync += stalled.eq(1)
                    m.d.sync += flushing.eq(1)

                m.d.sync += self.pc.eq(current_pc)
                with m.If(~cache_resp.error):
                    m.d.sync += current_pc.eq(current_pc + Mux(is_rvc, C(2, 3), C(4, 3)))

                self.cont(m, data=instr, pc=current_pc, access_fault=cache_resp.error, rvc=is_rvc)

        @def_method(m, self.stall)
        def _():
            # TODO:  implement this properly - This is a placeholder
            # and most likely won't work
            m.d.sync += stalled.eq(1)
            m.d.sync += flushing.eq(1)

        @def_method(m, self.verify_branch, ready=(stalled & ~flushing))
        def _(from_pc: Value, next_pc: Value):
            m.d.sync += cache_req_pc.eq(next_pc)
            m.d.sync += current_pc.eq(next_pc)
            m.d.sync += stalled.eq(0)

        return m
