from math import lcm
from amaranth import *
from amaranth.lib.data import ArrayLayout
from transactron.lib import BasicFifo, WideFifo, Semaphore, Pipe, ConnectTrans
from transactron.lib.metrics import *
from transactron.lib.simultaneous import condition
from transactron.utils import count_trailing_zeros, popcount, assign, StableSelectingNetwork, logging
from transactron.utils.transactron_helpers import make_layout
from transactron.utils.amaranth_ext.coding import PriorityEncoder
from transactron import *
from transactron.evlog import EventSource

from coreblocks.cache.iface import CacheInterface
from coreblocks.frontend.decoder.rvc import InstrDecompress, is_instr_compressed
from coreblocks.priv.pmp import PMPChecker, PMPOperationMode

from coreblocks.arch import *
from coreblocks.params import *
from coreblocks.interface.layouts import *
from coreblocks.frontend import FrontendParams
from coreblocks.priv.vmem.translation import AddressTranslator, AddressTranslatorMode
from coreblocks.telemetry import InstrFetched

log = logging.HardwareLogger("frontend.fetch")
evlog = EventSource("frontend.fetch")


class FetchUnit(Elaboratable):
    """Superscalar Fetch Unit

    This module is responsible for retrieving instructions from memory and forwarding them to the decode stage.

    It works with 'fetch blocks', chunks of data it handles at a time. The size of these blocks
    depends on GenParams.fetch_block_bytes and is related to how many instructions the unit can
    handle at once, which can vary if extension C is on.

    The unit also deals with expanding compressed instructions and managing instructions that aren't aligned to
    4-byte boundaries.
    """

    fetch_request: Provided[Method]
    """Requests a fetch of the instruction block at the given PC."""

    fetch_writeback: Required[Method]
    """Invoked to write back the status of the requested fetch block."""

    flush: Provided[Method]
    """Flushes the fetch unit from the currently processed fetch blocks, so it can be redirected or/and stalled."""

    cont: Required[Method]
    """Should be invoked to send fetched instruction to the next step."""

    stall_unsafe: Required[Method]
    """Called when an unsafe instruction is fetched."""

    check_stale: Required[Methods]
    """
    Asks the FTQ whether a fetch request is stale. One instance per stage (1 and 2).
    """

    read_prediction: Required[Method]
    """Return the branch prediction stored for a given FTQ entry. """

    def __init__(self, gen_params: GenParams, icache: CacheInterface) -> None:
        """
        Parameters
        ----------
        gen_params : GenParams
            Instance of GenParams with parameters which should be used to generate
            fetch unit.
        icache : CacheInterface
            Instruction Cache
        """
        self.gen_params = gen_params
        self.icache = icache
        self.stall_unsafe = Method()

        self.layouts = self.gen_params.get(FetchLayouts)

        self.cont = Method(i=self.layouts.fetch_result)
        self.fetch_request = Method(i=self.layouts.fetch_request)
        self.fetch_writeback = Method(i=self.layouts.fetch_writeback)
        self.check_stale = Methods(2, i=self.layouts.check_stale_req, o=self.layouts.check_stale_resp)
        self.read_prediction = Method(i=self.layouts.read_prediction_req, o=self.layouts.bpu_prediction)

        self.flush = Method()

        self.perf_fetch_utilization = TaggedCounter(
            "frontend.fetch.fetch_block_util",
            "Number of valid instructions in fetch blocks",
            tags=range(self.gen_params.fetch_width + 1),
        )

        self.addr_translator = AddressTranslator(self.gen_params, mode=AddressTranslatorMode.INSTRUCTION)

    def elaborate(self, platform):
        m = TModule()

        m.submodules += [self.perf_fetch_utilization]

        m.submodules.addr_translator = self.addr_translator

        fetch_width = self.gen_params.fetch_width
        fields = self.gen_params.get(CommonLayoutFields)
        params = self.gen_params.get(FrontendParams)

        # Serializer creates a continuous instruction stream from fetch
        # blocks, which can have holes in them.
        m.submodules.aligner = aligner = StableSelectingNetwork(fetch_width, self.layouts.raw_instr)
        serializer_depth = 2 * lcm(self.gen_params.frontend_superscalarity, fetch_width)
        m.submodules.serializer = serializer = WideFifo(
            self.layouts.raw_instr,
            depth=serializer_depth,
            read_width=self.gen_params.frontend_superscalarity,
            write_width=fetch_width,
        )

        with Transaction(name="cont").body(m):
            peek_result = serializer.peek(m)
            count = Signal(range(self.gen_params.frontend_superscalarity + 1))
            # we want at most one branch insn in scheduling group, and only at the end (for simplicity)
            # some insts in peek_result.data might not be valid, but this is still correct
            which_is_branch = [0] + [instr.cfi_type == CfiType.BRANCH for instr in peek_result.data][:-1]
            m.d.comb += count.eq(count_trailing_zeros(Cat(which_is_branch)))
            result = serializer.read(m, count=count)
            for i in range(self.gen_params.frontend_superscalarity):
                log.info(
                    m,
                    i < result.count,
                    "Sending an instr to the backend pc=0x{:x} instr=0x{:x}",
                    result.data[i].pc,
                    result.data[i].instr,
                )
            self.cont(m, result)

        m.submodules.fetch_requests = fetch_requests = BasicFifo(
            make_layout(fields.pc, ("access_fault", 1), ("page_fault", 1), fields.ftq_ptr, fields.fetch_gen),
            depth=2,
        )

        # This limits number of fetch blocks the fetch unit can process
        # at a time. We start counting when sending a request to the cache and
        # stop when pushing a fetch packet out of the fetch unit.
        max_inflight_requests = 4
        assert max_inflight_requests <= 2 ** make_layout(fields.fetch_gen).size
        m.submodules.req_counter = req_counter = Semaphore(max_inflight_requests)

        #
        # Fetch - stage 0
        # ================
        # - send a request to the instruction cache
        # - check PMP execute permission (if PMP is enabled)
        #

        m.submodules.pmp_checker = pmp_checker = PMPChecker(
            self.gen_params,
            mode=PMPOperationMode.INSTRUCTION_FETCH,
        )

        m.submodules.addr_translator_accept_pipe = addr_translator_accept_pipe = Pipe(
            self.addr_translator.accept.layout_out
        )
        m.submodules += ConnectTrans.create(self.addr_translator.accept, addr_translator_accept_pipe.write)

        m.submodules.ftq_ptr_pipe = ftq_ptr_pipe = Pipe(make_layout(fields.ftq_ptr, fields.fetch_gen))

        @def_method(m, self.fetch_request)
        def _(pc, ftq_ptr, fetch_gen):
            log.info(m, True, "[IFU] request pc=0x{:x}", pc)
            req_counter.acquire(m)

            self.addr_translator.request(m, addr=pc, is_store=0)
            ftq_ptr_pipe.write(m, ftq_ptr=ftq_ptr, fetch_gen=fetch_gen)

        with Transaction().body(m):
            translated = addr_translator_accept_pipe.read(m)
            request_id = ftq_ptr_pipe.read(m)
            access_fault = Signal()

            m.d.av_comb += pmp_checker.paddr.eq(translated.paddr)
            m.d.av_comb += access_fault.eq(translated.access_fault | ~pmp_checker.result.x)

            with m.If(~translated.page_fault & ~access_fault):
                self.icache.issue_req(m, paddr=translated.paddr)

            fetch_requests.write(
                m,
                pc=translated.vaddr,
                access_fault=access_fault,
                page_fault=translated.page_fault,
                ftq_ptr=request_id.ftq_ptr,
                fetch_gen=request_id.fetch_gen,
            )

        #
        # State passed between stage 1 and stage 2
        #
        m.submodules.s1_s2_pipe = s1_s2_pipe = Pipe(
            [
                fields.fb_addr,
                fields.ftq_ptr,
                fields.fetch_gen,
                ("instr_valid", fetch_width),
                ("access_fault", FetchLayouts.FaultFlag),
                ("rvc", fetch_width),
                ("instrs", ArrayLayout(self.gen_params.isa.ilen, fetch_width)),
                ("starts_mid_instr", 1),
                ("ends_mid_instr", 1),
                ("last_half", 16),
            ]
        )

        #
        # Fetch - stage 1
        # ================
        # - read the response from the cache
        # - expand compressed instructions (if applicable)
        # - find where each instruction begins
        # - handle instructions that cross a fetch boundary
        #
        rvc_expanders = [InstrDecompress(self.gen_params) for _ in range(fetch_width)]
        for n, module in enumerate(rvc_expanders):
            m.submodules[f"rvc_expander_{n}"] = module

        # With the C extension enabled, a single instruction can
        # be located on a boundary of two fetch blocks. Hence,
        # this requires some statefulness of the stage 1.
        prev_half = Signal(16)
        prev_half_addr = Signal(make_layout(fields.fb_addr).size)
        prev_half_v = Signal()
        with Transaction(name="Fetch_Stage1").body(m):
            fetch_request = fetch_requests.read(m)

            s1_stale = self.check_stale[0](m, ftq_ptr=fetch_request.ftq_ptr, fetch_gen=fetch_request.fetch_gen).stale

            # The address of the fetch block.
            fetch_block_addr = params.fb_addr(fetch_request.pc)
            # The index (in instructions) of the first instruction that we should process.
            fetch_block_offset = params.fb_instr_idx(fetch_request.pc)

            # Conditionally read from icache or mark fault
            cache_resp = Signal(self.gen_params.get(ICacheLayouts).accept_res)
            access_fault = Signal(FetchLayouts.FaultFlag)

            with condition(m, nonblocking=True) as branch:
                with branch(~fetch_request.page_fault & ~fetch_request.access_fault):
                    m.d.av_comb += cache_resp.eq(self.icache.accept_res(m))

            with m.If(fetch_request.page_fault):
                m.d.av_comb += access_fault.eq(FetchLayouts.FaultFlag.PAGE_FAULT)
            with m.Elif(fetch_request.access_fault | cache_resp.error):
                m.d.av_comb += access_fault.eq(FetchLayouts.FaultFlag.ACCESS_FAULT)

            #
            # Expand compressed instructions from the fetch block.
            #
            expanded_instr = [Signal(self.gen_params.isa.ilen) for _ in range(fetch_width)]
            is_rvc = Signal(fetch_width)

            # Whether in this cycle we have a fetch block that contains
            # an instruction that crosses a fetch boundary
            starts_mid_instr = Signal()
            m.d.av_comb += starts_mid_instr.eq(prev_half_v & ((prev_half_addr + 1) == fetch_block_addr))

            for i in range(fetch_width):
                if Extension.ZCA in self.gen_params.isa.extensions:
                    full_instr = Signal(self.gen_params.isa.ilen)
                    if i == 0:
                        # If we have a half of an instruction from the previous block - we need to use it now.
                        with m.If(starts_mid_instr):
                            m.d.av_comb += full_instr.eq(Cat(prev_half, cache_resp.fetch_block[0:16]))
                        with m.Else():
                            m.d.av_comb += full_instr.eq(cache_resp.fetch_block[:32])
                    elif i == fetch_width - 1:
                        # We will have only 16 bits for the last instruction, so append 16 zeroes.
                        m.d.av_comb += full_instr.eq(Cat(cache_resp.fetch_block[-16:], C(0, 16)))
                    else:
                        m.d.av_comb += full_instr.eq(cache_resp.fetch_block[i * 16 : i * 16 + 32])

                    m.d.av_comb += is_rvc[i].eq(is_instr_compressed(full_instr))
                    m.d.av_comb += rvc_expanders[i].instr_in.eq(full_instr[:16])
                    m.d.av_comb += expanded_instr[i].eq(Mux(is_rvc[i], rvc_expanders[i].instr_out, full_instr))
                else:
                    m.d.av_comb += expanded_instr[i].eq(cache_resp.fetch_block[i * 32 : (i + 1) * 32])

            # Mask denoting at which offsets expected instructions start (depends on rvc indication and start address)
            instr_start = [Signal() for _ in range(fetch_width)]
            for i in range(fetch_width):
                if Extension.ZCA in self.gen_params.isa.extensions:
                    if i == 0:
                        m.d.av_comb += instr_start[i].eq(fetch_block_offset == 0)
                    elif i == 1:
                        m.d.av_comb += instr_start[i].eq(
                            (fetch_block_offset <= i) & (~instr_start[0] | is_rvc[0] | starts_mid_instr)
                        )
                    else:
                        m.d.av_comb += instr_start[i].eq(
                            (fetch_block_offset <= i) & (~instr_start[i - 1] | is_rvc[i - 1])
                        )
                else:
                    m.d.av_comb += instr_start[i].eq(fetch_block_offset <= i)

            ends_mid_instr = Signal()

            if Extension.ZCA in self.gen_params.isa.extensions:
                instr_position_mask = Cat(instr_start[:-1], instr_start[-1] & is_rvc[-1])

                m.d.av_comb += ends_mid_instr.eq(~access_fault.any() & ~is_rvc[-1] & instr_start[-1])

                # Only a live block may update the cross-fetch carry
                with m.If(~s1_stale):
                    m.d.sync += prev_half_v.eq(ends_mid_instr)
                    m.d.sync += prev_half.eq(cache_resp.fetch_block[-16:])
                    m.d.sync += prev_half_addr.eq(fetch_block_addr)
            else:
                instr_position_mask = Cat(instr_start)

            # Reported fault pc (signalled by emitting an instruction) must always match first requested instruction
            access_fault_instr_position = 1 << fetch_block_offset

            s1_s2_pipe.write(
                m,
                fb_addr=fetch_block_addr,
                instr_valid=Mux(access_fault.any(), access_fault_instr_position, instr_position_mask),
                access_fault=access_fault,
                rvc=is_rvc,
                ftq_ptr=fetch_request.ftq_ptr,
                fetch_gen=fetch_request.fetch_gen,
                instrs=expanded_instr,
                starts_mid_instr=starts_mid_instr,
                ends_mid_instr=ends_mid_instr,
                last_half=cache_resp.fetch_block[-16:],
            )

        #
        # Fetch - stage 2
        # ================
        # - predecode instructions
        # - verify the branch prediction
        # - redirect the frontend if mispredicted
        # - check if any of instructions stalls the frontend
        # - enqueue a packet of instructions
        #

        predecoders = [Predecoder(self.gen_params) for _ in range(fetch_width)]
        for n, module in enumerate(predecoders):
            m.submodules[f"predecoder_{n}"] = module

        m.submodules.prediction_checker = prediction_checker = PredictionChecker(self.gen_params)

        with Transaction(name="Fetch_Stage2").body(m):
            req_counter.release(m)
            s1_data = s1_s2_pipe.read(m)

            ftq_ptr = s1_data.ftq_ptr
            instrs = s1_data.instrs
            fetch_block_addr = s1_data.fb_addr
            instr_valid = s1_data.instr_valid
            access_fault = s1_data.access_fault
            fault_any = Signal()
            m.d.av_comb += fault_any.eq(access_fault.any())

            # Predecode instructions
            predecoded_instr = [predecoders[i].predecode(m, instrs[i]) for i in range(fetch_width)]

            s2_stale = self.check_stale[1](m, ftq_ptr=ftq_ptr, fetch_gen=s1_data.fetch_gen).stale

            with m.If(~s2_stale):
                prediction = self.read_prediction(m, ftq_ptr=ftq_ptr)

                predcheck_res = prediction_checker.check(
                    m,
                    fb_addr=fetch_block_addr,
                    starts_mid_instr=s1_data.starts_mid_instr,
                    instr_valid=instr_valid,
                    predecoded=predecoded_instr,
                    prediction=prediction,
                )

            # Is the instruction unsafe (i.e. stalls the frontend until the backend resumes it).
            instr_unsafe = Signal(fetch_width)
            for i in range(fetch_width):
                # If there was an access fault, mark every instruction as unsafe
                m.d.av_comb += instr_unsafe[i].eq((predecoded_instr[i].unsafe | fault_any) & instr_valid[i])

            m.submodules.unsafe_prio_encoder = unsafe_prio_encoder = PriorityEncoder(fetch_width)
            m.d.av_comb += unsafe_prio_encoder.i.eq(instr_unsafe)

            unsafe_idx = unsafe_prio_encoder.o[: self.gen_params.fetch_width_log]
            has_unsafe = Signal()
            m.d.av_comb += has_unsafe.eq(~unsafe_prio_encoder.n)

            # Is there any control flow instruction that we should follow?
            cfi_followed = Signal()
            m.d.av_comb += cfi_followed.eq(CfiType.valid(predcheck_res.cfi_type))

            # The point where control leaves the block (its "exit")
            # If we didn't follow any CFI, then our exit point is the last instruction
            exit_idx = Signal(range(fetch_width))
            exit_target = Signal(self.gen_params.isa.xlen)
            m.d.av_comb += [
                exit_idx.eq(Mux(cfi_followed, predcheck_res.cfi_idx, fetch_width - 1)),
                exit_target.eq(Mux(cfi_followed, predcheck_res.cfi_target, params.pc_from_fb(fetch_block_addr + 1, 0))),
            ]

            # The exit is always reached, unless an unsafe instruction comes before it
            exit_reached = Signal()
            m.d.av_comb += exit_reached.eq(~has_unsafe | (exit_idx < unsafe_idx))

            # A JALR's target cannot be computed from predecode, so a mispredicted JALR
            # can't redirect - we stall until the backend executes it instead
            eff_cfi_valid = Signal()
            eff_redirect_target = Signal(self.gen_params.isa.xlen)
            m.d.av_comb += eff_cfi_valid.eq(~CfiType.is_jalr(predcheck_res.cfi_type))
            m.d.av_comb += eff_redirect_target.eq(exit_target)

            mispredict = Signal()
            m.d.av_comb += mispredict.eq(predcheck_res.mispredicted)

            # Stall either on an unsafe instruction cutting the block (~exit_reached), or on
            # an exit through a mispredicted JALR whose target we don't know (~eff_cfi_valid)
            redirect = Signal()
            stall_core = Signal()
            m.d.av_comb += redirect.eq(exit_reached & mispredict & eff_cfi_valid)
            m.d.av_comb += stall_core.eq(~exit_reached | (mispredict & ~eff_cfi_valid))

            # Index of the last instruction of the block: the exit, or the unsafe instruction
            # that cut the block before it
            block_end_idx = Signal(range(fetch_width))
            m.d.av_comb += block_end_idx.eq(Mux(exit_reached, exit_idx, unsafe_idx))

            # The mask that denotes what prefix of instructions we should enqueue
            block_prefix_mask = Signal(fetch_width)
            m.d.av_comb += block_prefix_mask.eq((1 << (block_end_idx + 1)) - 1)

            # The ultimate mask that tells which instructions should be sent to the backend
            fetch_mask = Signal(fetch_width)
            m.d.av_comb += fetch_mask.eq(instr_valid & block_prefix_mask)

            # Aggregate all signals that will be sent out of the fetch unit.
            raw_instrs = Signal(ArrayLayout(self.layouts.raw_instr, fetch_width))
            for i in range(fetch_width):
                m.d.av_comb += [
                    raw_instrs[i].instr.eq(instrs[i]),
                    raw_instrs[i].pc.eq(params.pc_from_fb(fetch_block_addr, i)),
                    raw_instrs[i].rvc.eq(s1_data.rvc[i]),
                    raw_instrs[i].access_fault.eq(s1_data.access_fault),
                    raw_instrs[i].cfi_type.eq(predecoded_instr[i].cfi_type),
                    raw_instrs[i].ftq_ptr.eq(ftq_ptr),
                    raw_instrs[i].ftq_offset.eq(i),
                ]

            if Extension.ZCA in self.gen_params.isa.extensions:
                with m.If(s1_data.starts_mid_instr):
                    m.d.av_comb += raw_instrs[0].pc.eq(params.pc_from_fb(fetch_block_addr, 0) - 2)
                    with m.If(s1_data.access_fault):
                        # Mark that access/page fault happened only at second (current) half.
                        # If fault happened on the first half `starts_mid_instr` would be false
                        m.d.av_comb += raw_instrs[0].access_fault.eq(
                            s1_data.access_fault | FetchLayouts.FaultFlag.EXCEPTION_ON_SECOND_HALF
                        )

            with m.If(~s2_stale):
                with m.If(fault_any | stall_core):
                    self.stall_unsafe(m)

                self.fetch_writeback(
                    m,
                    ftq_ptr=ftq_ptr,
                    redirect=redirect,
                    stall=fault_any | stall_core,
                    cfi_idx=exit_idx,
                    cfi_type=predcheck_res.cfi_type,
                    cfi_target=eff_redirect_target,
                )

                # The cross-fetch carry is dropped whenever this block breaks the
                # sequential fetch stream (redirect/fault/stall), with one exception: a
                # fall-through resteer (a predicted CFI decoded as a non-CFI; cfi_type is
                # INVALID) steers to the next sequential block, so this whole block is on-path
                # and the carry must be re-established instead.
                if Extension.ZCA in self.gen_params.isa.extensions:
                    with m.If(redirect & s1_data.ends_mid_instr & ~CfiType.valid(predcheck_res.cfi_type)):
                        m.d.sync += [
                            prev_half_v.eq(1),
                            prev_half.eq(s1_data.last_half),
                            prev_half_addr.eq(fetch_block_addr),
                        ]
                    with m.Elif(fault_any | stall_core | redirect):
                        m.d.sync += prev_half_v.eq(0)

                self.perf_fetch_utilization.incr(m, popcount(fetch_mask))

                for i in range(fetch_width):
                    evlog.emit(
                        m,
                        InstrFetched.hw(
                            ftq_ptr=ftq_ptr,
                            pc=raw_instrs[i].pc,
                            instr=raw_instrs[i].instr,
                            ftq_offset=i,
                        ),
                        when=fetch_mask[i],
                    )

                # Make sure this is called only once to avoid a huge mux on arguments
                m.d.av_comb += [aligner.valids.eq(fetch_mask), aligner.inputs.eq(raw_instrs)]
                serializer.write(m, data=aligner.outputs, count=aligner.output_cnt)

        @def_method(m, self.flush)
        def _():
            m.d.sync += prev_half_v.eq(0)
            serializer.clear(m)

        return m


class Predecoder(Elaboratable):
    """Instruction predecoder

    The module performs basic analysis on instructions. It identifies if an instruction
    is a jump instruction, determines the type of jump, and finds the jump's target.

    Its role is to give quick feedback to the fetch unit and potentially the branch predictor
    about the fetched instruction. This helps in redirecting the fetch unit promptly if needed.
    """

    def __init__(self, gen_params: GenParams) -> None:
        """
        Parameters
        ----------
        gen_params: GenParams
            Core generation parameters.
        """
        self.gen_params = gen_params

        layouts = self.gen_params.get(FetchLayouts)
        fields = self.gen_params.get(CommonLayoutFields)

        self.predecode = Method(i=make_layout(fields.instr), o=layouts.predecoded_instr)

    def elaborate(self, platform):
        m = TModule()

        @def_method(m, self.predecode)
        def _(instr):
            quadrant = instr[0:2]
            opcode = instr[2:7]
            funct3 = instr[12:15]
            rd = instr[7:12]
            rs1 = instr[15:20]

            bimm = Signal(signed(13))
            jimm = Signal(signed(21))
            iimm = Signal(signed(12))

            m.d.av_comb += [
                iimm.eq(instr[20:]),
                bimm.eq(Cat(0, instr[8:12], instr[25:31], instr[7], instr[31])),
                jimm.eq(Cat(0, instr[21:31], instr[20], instr[12:20], instr[31])),
            ]

            ret = Signal.like(self.predecode.data_out)

            with m.Switch(opcode):
                with m.Case(Opcode.BRANCH):
                    m.d.av_comb += ret.cfi_type.eq(CfiType.BRANCH)
                    m.d.av_comb += ret.cfi_offset.eq(bimm)
                with m.Case(Opcode.JAL):
                    m.d.av_comb += ret.cfi_type.eq(
                        Mux((rd == Registers.X1) | (rd == Registers.X5), CfiType.CALL, CfiType.JAL)
                    )
                    m.d.av_comb += ret.cfi_offset.eq(jimm)
                with m.Case(Opcode.JALR):
                    m.d.av_comb += ret.cfi_type.eq(
                        Mux((rs1 == Registers.X1) | (rs1 == Registers.X5), CfiType.RET, CfiType.JALR)
                    )
                    m.d.av_comb += ret.cfi_offset.eq(iimm)
                with m.Default():
                    m.d.av_comb += ret.cfi_type.eq(CfiType.INVALID)

            with m.If(quadrant != 0b11):
                m.d.av_comb += ret.cfi_type.eq(CfiType.INVALID)

            m.d.av_comb += ret.unsafe.eq(
                (opcode == Opcode.SYSTEM) | ((opcode == Opcode.MISC_MEM) & (funct3 == Funct3.FENCEI))
            )

            return ret

        return m


class PredictionChecker(Elaboratable):
    """Branch prediction checker

    This module checks if branch predictions are correct by looking at predecoded data.
    It checks for the following errors:

     - a JAL/JALR instruction was not predicted taken,
     - mistaking non-control flow instructions (CFI) for control flow ones,
     - getting the target of JAL/BRANCH instructions wrong.
    """

    def __init__(self, gen_params: GenParams) -> None:
        """
        Parameters
        ----------
        gen_params: GenParams
            Core generation parameters.
        """
        self.gen_params = gen_params

        layouts = gen_params.get(FetchLayouts)

        self.check = Method(i=layouts.pred_checker_i, o=layouts.pred_checker_o)

        self.perf_preceding_redirection = TaggedCounter(
            "frontend.fetch.pred_checker.preceding_redirection",
            "Number of redirections caused by undetected CFIs",
            tags=CfiType,
        )
        self.perf_mispredicted_cfi_type = TaggedCounter(
            "frontend.fetch.pred_checker.cfi_type_mispredict",
            "Number of redirections caused by misprediction of the CFI type",
            tags=CfiType,
        )
        self.perf_mispredicted_cfi_target = TaggedCounter(
            "frontend.fetch.pred_checker.cfi_target_mispredict",
            "Number of redirections caused by misprediction of the CFI target",
            tags=CfiType,
        )

    def elaborate(self, platform):
        m = TModule()

        params = self.gen_params.get(FrontendParams)

        m.submodules += [
            self.perf_mispredicted_cfi_type,
            self.perf_preceding_redirection,
            self.perf_mispredicted_cfi_target,
        ]

        @def_method(m, self.check)
        def _(fb_addr, starts_mid_instr, instr_valid, predecoded, prediction):
            decoded_cfi_types = Array([predecoded[i].cfi_type for i in range(self.gen_params.fetch_width)])
            decoded_cfi_offsets = Array([predecoded[i].cfi_offset for i in range(self.gen_params.fetch_width)])

            # First find all the instructions that would redirect the fetch unit.
            decoded_redirections = Signal(self.gen_params.fetch_width)
            for i in range(self.gen_params.fetch_width):
                # Here we make a static prediction: forward branches not taken and backward
                # taken. This prediction will be used if the branch prediction unit
                # didn't detect the branch at all.
                m.d.av_comb += decoded_redirections[i].eq(
                    CfiType.is_jal(decoded_cfi_types[i])
                    | CfiType.is_jalr(decoded_cfi_types[i])
                    | (
                        CfiType.is_branch(decoded_cfi_types[i])
                        & ~prediction.branch_mask[i]
                        & (decoded_cfi_offsets[i] < 0)
                    )
                )

            # Find the earliest one
            m.submodules.pd_redirection_enc = pd_redirection_enc = PriorityEncoder(self.gen_params.fetch_width)
            m.d.av_comb += pd_redirection_enc.i.eq(decoded_redirections & instr_valid)

            pd_redirect_idx = Signal(self.gen_params.fetch_width_log)
            m.d.av_comb += pd_redirect_idx.eq(pd_redirection_enc.o[: self.gen_params.fetch_width_log])

            # For a given instruction index, returns a CFI target based on the predecode info
            def get_decoded_target_for(idx: Value) -> Value:
                base = params.pc_from_fb(fb_addr, idx) + decoded_cfi_offsets[idx]
                if Extension.ZCA in self.gen_params.isa.extensions:
                    return base - Mux(starts_mid_instr & (idx == 0), 2, 0)
                return base

            # Target of a CFI that would redirect the frontend according to the prediction
            decoded_target_for_predicted_cfi = Signal(self.gen_params.isa.xlen)
            m.d.av_comb += decoded_target_for_predicted_cfi.eq(get_decoded_target_for(prediction.cfi_idx))

            # Target of a CFI that would redirect the frontend according to predecode info
            decoded_target_for_decoded_cfi = Signal(self.gen_params.isa.xlen)
            m.d.av_comb += decoded_target_for_decoded_cfi.eq(get_decoded_target_for(pd_redirect_idx))

            preceding_redirection = ~pd_redirection_enc.n & (
                ((CfiType.valid(prediction.cfi_type) & (pd_redirect_idx < prediction.cfi_idx)))
                | ~CfiType.valid(prediction.cfi_type)
            )

            decoded_cfi_type_at_pred = Mux(
                instr_valid.bit_select(prediction.cfi_idx, 1),
                decoded_cfi_types[prediction.cfi_idx],
                CfiType.INVALID,
            )

            mispredicted_cfi_type = CfiType.valid(prediction.cfi_type) & (
                prediction.cfi_type != decoded_cfi_type_at_pred
            )

            mispredicted_cfi_target = (CfiType.is_branch(prediction.cfi_type) | CfiType.is_jal(prediction.cfi_type)) & (
                ~prediction.cfi_target_valid | (decoded_target_for_predicted_cfi != prediction.cfi_target)
            )

            ret = Signal.like(self.check.data_out)

            with m.If(preceding_redirection):
                self.perf_preceding_redirection.incr(m, decoded_cfi_types[pd_redirect_idx])
                m.d.av_comb += assign(
                    ret,
                    {
                        "mispredicted": 1,
                        "cfi_idx": pd_redirect_idx,
                        "cfi_type": decoded_cfi_types[pd_redirect_idx],
                        "cfi_target": decoded_target_for_decoded_cfi,
                    },
                )
            with m.Elif(mispredicted_cfi_type):
                self.perf_mispredicted_cfi_type.incr(m, prediction.cfi_type)
                # If no decoded instruction redirects (pd_redirection_enc.n), this is a
                # fall-through resteer: cfi_type is INVALID and cfi_idx/cfi_target are
                # meaningless.
                m.d.av_comb += assign(
                    ret,
                    {
                        "mispredicted": 1,
                        "cfi_idx": pd_redirect_idx,
                        "cfi_type": Mux(pd_redirection_enc.n, CfiType.INVALID, decoded_cfi_types[pd_redirect_idx]),
                        "cfi_target": decoded_target_for_decoded_cfi,
                    },
                )
            with m.Elif(mispredicted_cfi_target):
                self.perf_mispredicted_cfi_target.incr(m, prediction.cfi_type)
                m.d.av_comb += assign(
                    ret,
                    {
                        "mispredicted": 1,
                        "cfi_idx": prediction.cfi_idx,
                        "cfi_type": decoded_cfi_types[prediction.cfi_idx],
                        "cfi_target": decoded_target_for_predicted_cfi,
                    },
                )
            with m.Else():
                m.d.av_comb += assign(
                    ret,
                    {
                        "mispredicted": 0,
                        "cfi_idx": prediction.cfi_idx,
                        "cfi_type": prediction.cfi_type,
                        "cfi_target": prediction.cfi_target,
                    },
                )

            return ret

        return m
