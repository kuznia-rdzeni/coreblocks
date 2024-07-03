from amaranth import *
from amaranth.lib.data import ArrayLayout
from amaranth.lib.coding import PriorityEncoder

from transactron.lib import BasicFifo, Semaphore, ConnectTrans, logging, Pipe
from transactron.lib.metrics import *
from transactron.lib.simultaneous import condition
from transactron.utils import MethodLayout, popcount, assign, MultiPriorityEncoder
from transactron.utils.transactron_helpers import from_method_layout, make_layout
from transactron import *

from coreblocks.cache.iface import CacheInterface
from coreblocks.frontend.decoder.rvc import InstrDecompress, is_instr_compressed
from coreblocks.arch import *
from coreblocks.params import *
from coreblocks.interface.layouts import *
from coreblocks.frontend import FrontendParams

log = logging.HardwareLogger("frontend.fetch")


class FetchUnit(Elaboratable):
    """Superscalar Fetch Unit

    This module is responsible for retrieving instructions from memory and forwarding them to the decode stage.

    It works with 'fetch blocks', chunks of data it handles at a time. The size of these blocks
    depends on GenParams.fetch_block_bytes and is related to how many instructions the unit can
    handle at once, which can vary if extension C is on.

    The unit also deals with expanding compressed instructions and managing instructions that aren't aligned to
    4-byte boundaries.
    """

    def __init__(
        self,
        gen_params: GenParams,
        icache: CacheInterface,
        cont: Method,
        consume_fetch_target: Method,
        consume_prediction: Method,
        ftq_writeback: Method,
    ) -> None:
        """
        Parameters
        ----------
        gen_params : GenParams
            Instance of GenParams with parameters which should be used to generate
            fetch unit.
        icache : CacheInterface
            Instruction Cache
        cont : Method
            Method which should be invoked to send fetched instruction to the next step.
            It has layout as described by `FetchLayout`.
        """
        self.gen_params = gen_params
        self.icache = icache
        self.cont = cont

        self.consume_fetch_target = consume_fetch_target
        self.consume_prediction = consume_prediction
        self.ftq_writeback = ftq_writeback

        self.layouts = self.gen_params.get(FetchLayouts)

        self.flush = Method(nonexclusive=True)

        self.perf_fetch_utilization = TaggedCounter(
            "frontend.fetch.fetch_block_util",
            "Number of valid instructions in fetch blocks",
            tags=range(self.gen_params.fetch_width + 1),
        )
        self.perf_fetch_redirects = HwCounter(
            "frontend.fetch.fetch_redirects", "How many times the fetch unit redirected itself"
        )

    def elaborate(self, platform):
        m = TModule()

        m.submodules += [self.perf_fetch_utilization, self.perf_fetch_redirects]

        fetch_width = self.gen_params.fetch_width
        fields = self.gen_params.get(CommonLayoutFields)
        params = self.gen_params.get(FrontendParams)

        # Serializer is just a temporary workaround until we have a proper multiport FIFO
        # to which we can push bundles of instructions.
        m.submodules.serializer = serializer = Serializer(fetch_width, self.layouts.raw_instr)
        m.submodules.serializer_connector = ConnectTrans(serializer.read, self.cont)

        fields = self.gen_params.get(CommonLayoutFields)

        # This limits number of fetch blocks the fetch unit can process
        # at a time. We start counting when sending a request to the cache and
        # stop when pushing a fetch packet out of the fetch unit.
        m.submodules.req_counter = req_counter = Semaphore(4)
        flushing_counter = Signal.like(req_counter.count)

        #
        # State passed between stage 0 and stage 1
        #
        m.submodules.s0_s1_fifo = s0_s1_fifo = BasicFifo(layout=[fields.ftq_idx, fields.pc, fields.bpu_stage], depth=2)

        #
        # Fetch - stage 0
        # ================
        # - consume a fetch target from the FTQ
        # - send a request to the instruction cache
        #
        with Transaction(name="Fetch_Stage0").body(m):
            req_counter.acquire(m)

            fetch_target = self.consume_fetch_target(m)

            self.icache.issue_req(m, addr=fetch_target.pc)
            s0_s1_fifo.write(m, fetch_target)

            log.info(
                m,
                True,
                "IFU Stage 0 FTQ={}/{} pc=0x{:x}",
                fetch_target.ftq_idx.parity,
                fetch_target.ftq_idx.ptr,
                fetch_target.pc,
            )

        #
        # State passed between stage 1 and stage 2
        #
        m.submodules.s1_s2_pipe = s1_s2_pipe = Pipe(
            [
                fields.ftq_idx,
                fields.fb_addr,
                fields.bpu_stage,
                ("instr_valid", fetch_width),
                ("access_fault", 1),
                ("rvc", fetch_width),
                ("instrs", ArrayLayout(self.gen_params.isa.ilen, fetch_width)),
                ("instr_block_cross", 1),
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
        prev_half_addr = Signal(make_layout(fields.fb_addr))
        prev_half_v = Signal()

        with Transaction(name="Fetch_Stage1").body(m):
            target = s0_s1_fifo.read(m)
            cache_resp = self.icache.accept_res(m)

            log.info(m, True, "IFU Stage 1 FTQ={}/{}", target.ftq_idx.parity, target.ftq_idx.ptr)

            # The address of the fetch block.
            fetch_block_addr = params.fb_addr(target.pc)
            # The index (in instructions) of the first instruction that we should process.
            fetch_block_offset = params.fb_instr_idx(target.pc)

            #
            # Expand compressed instructions from the fetch block.
            #
            expanded_instr = [Signal(self.gen_params.isa.ilen) for _ in range(fetch_width)]
            is_rvc = Signal(fetch_width)

            # Whether in this cycle we have a fetch block that contains
            # an instruction that crosses a fetch boundary
            instr_block_cross = Signal()
            m.d.av_comb += instr_block_cross.eq(prev_half_v & ((prev_half_addr.fb_addr + 1) == fetch_block_addr))

            for i in range(fetch_width):
                if Extension.C in self.gen_params.isa.extensions:
                    full_instr = Signal(self.gen_params.isa.ilen)
                    if i == 0:
                        # If we have a half of an instruction from the previous block - we need to use it now.
                        with m.If(instr_block_cross):
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

            # Mask denoting at which offsets an instruction starts
            instr_start = [Signal() for _ in range(fetch_width)]
            for i in range(fetch_width):
                if Extension.C in self.gen_params.isa.extensions:
                    if i == 0:
                        m.d.av_comb += instr_start[i].eq(fetch_block_offset == 0)
                    elif i == 1:
                        m.d.av_comb += instr_start[i].eq(
                            (fetch_block_offset <= i) & (~instr_start[0] | is_rvc[0] | instr_block_cross)
                        )
                    else:
                        m.d.av_comb += instr_start[i].eq(
                            (fetch_block_offset <= i) & (~instr_start[i - 1] | is_rvc[i - 1])
                        )
                else:
                    m.d.av_comb += instr_start[i].eq(fetch_block_offset <= i)

            if Extension.C in self.gen_params.isa.extensions:
                valid_instr_mask = Cat(instr_start[:-1], instr_start[-1] & is_rvc[-1])

                m.d.sync += prev_half_v.eq(
                    (flushing_counter <= 1) & (cache_resp.error == 0) & ~is_rvc[-1] & instr_start[-1]
                )
                m.d.sync += prev_half.eq(cache_resp.fetch_block[-16:])
                m.d.sync += prev_half_addr.fb_addr.eq(fetch_block_addr)
            else:
                valid_instr_mask = Cat(instr_start)

            s1_s2_pipe.write(
                m,
                ftq_idx=target.ftq_idx,
                fb_addr=fetch_block_addr,
                bpu_stage=target.bpu_stage,
                instr_valid=valid_instr_mask,
                access_fault=cache_resp.error,
                rvc=is_rvc,
                instrs=expanded_instr,
                instr_block_cross=instr_block_cross,
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

            instrs = s1_data.instrs
            fetch_block_addr = s1_data.fb_addr
            instr_valid = s1_data.instr_valid
            access_fault = s1_data.access_fault

            # Predecode instructions
            predecoded_instr = [predecoders[i].predecode(m, instrs[i]) for i in range(fetch_width)]

            with condition(m) as branch:
                with branch(flushing_counter == 0):
                    pred_data = self.consume_prediction(m, ftq_idx=s1_data.ftq_idx, bpu_stage=s1_data.bpu_stage)
                with branch(flushing_counter != 0):
                    pass

            log.info(
                m,
                True,
                "IFU Stage 2 FTQ={}/{} discard={} flushing={} run={}",
                s1_data.ftq_idx.parity,
                s1_data.ftq_idx.ptr,
                pred_data.discard,
                flushing_counter,
                self.consume_prediction.run,
            )

            # The method is guarded by the If to make sure that the metrics
            # are updated only if not flushing.
            with m.If((flushing_counter == 0) & ~pred_data.discard):
                predcheck_res = prediction_checker.check(
                    m,
                    fb_addr=fetch_block_addr,
                    instr_block_cross=s1_data.instr_block_cross,
                    instr_valid=instr_valid,
                    predecoded=predecoded_instr,
                    block_prediction=pred_data.block_prediction,
                )

            # Is the instruction unsafe (i.e. stalls the frontend until the backend resumes it).
            instr_unsafe = Signal(fetch_width)
            for i in range(fetch_width):
                # If there was an access fault, mark every instruction as unsafe
                m.d.av_comb += instr_unsafe[i].eq((predecoded_instr[i].unsafe | access_fault) & instr_valid[i])

            m.submodules.unsafe_prio_encoder = unsafe_prio_encoder = PriorityEncoder(fetch_width)
            m.d.av_comb += unsafe_prio_encoder.i.eq(instr_unsafe)

            unsafe_idx = unsafe_prio_encoder.o[: self.gen_params.fetch_width_log]
            has_unsafe = Signal()
            m.d.av_comb += has_unsafe.eq(~unsafe_prio_encoder.n)

            last_in_instr_valid, _ = MultiPriorityEncoder.create_simple(
                m, self.gen_params.fetch_width, instr_valid[::-1]
            )

            redirection_idx = Signal(range(fetch_width))
            m.d.av_comb += redirection_idx.eq(
                Mux(
                    CfiType.valid(predcheck_res.block_prediction.cfi_type),
                    predcheck_res.block_prediction.cfi_idx,
                    (self.gen_params.fetch_width - 1) - last_in_instr_valid,
                )
            )

            redirect = Signal()
            unsafe_stall = Signal()
            last_instr_idx = Signal(range(fetch_width))

            with m.If(~has_unsafe | (redirection_idx < unsafe_idx)):
                m.d.av_comb += [
                    redirect.eq(predcheck_res.mispredicted),
                    last_instr_idx.eq(redirection_idx),
                ]
            with m.Elif(has_unsafe):
                m.d.av_comb += [
                    unsafe_stall.eq(1),
                    last_instr_idx.eq(unsafe_idx),
                ]

            # This mask denotes what prefix of instructions we should enqueue.
            valid_instr_prefix = Signal(fetch_width)
            with m.If(redirect | unsafe_stall):
                # If there is an instruction that redirects or stalls the frontend, enqueue
                # instructions only up to that instruction.
                m.d.av_comb += valid_instr_prefix.eq((1 << (last_instr_idx + 1)) - 1)
            with m.Else():
                m.d.av_comb += valid_instr_prefix.eq(C(1).replicate(fetch_width))

            # The ultimate mask that tells which instructions should be sent to the backend.
            fetch_mask = Signal(fetch_width)
            m.d.av_comb += fetch_mask.eq(instr_valid & valid_instr_prefix)

            # Aggregate all signals that will be sent out of the fetch unit.
            raw_instrs = [Signal(self.layouts.raw_instr) for _ in range(fetch_width)]
            for i in range(fetch_width):
                m.d.av_comb += [
                    raw_instrs[i].ftq_addr.ftq_idx.eq(s1_data.ftq_idx),
                    raw_instrs[i].ftq_addr.fb_instr_idx.eq(i),
                    raw_instrs[i].instr.eq(instrs[i]),
                    raw_instrs[i].pc.eq(params.pc_from_fb(fetch_block_addr, i)),
                    raw_instrs[i].access_fault.eq(access_fault),
                    raw_instrs[i].rvc.eq(s1_data.rvc[i]),
                    raw_instrs[i].predicted_taken.eq(redirect & (predcheck_res.block_prediction.cfi_idx == i)),
                ]

            if Extension.C in self.gen_params.isa.extensions:
                with m.If(s1_data.instr_block_cross):
                    m.d.av_comb += raw_instrs[0].pc.eq(params.pc_from_fb(fetch_block_addr, 0) - 2)

            with condition(m, priority=False) as branch:
                with branch((flushing_counter == 0) & ~pred_data.discard):
                    self.perf_fetch_redirects.incr(m, cond=redirect)
                    self.perf_fetch_utilization.incr(m, popcount(fetch_mask))

                    with m.If(access_fault | unsafe_stall | redirect):
                        self.flush(m)

                    self.ftq_writeback(
                        m,
                        ftq_idx=s1_data.ftq_idx,
                        fb_addr=fetch_block_addr,
                        fb_last_instr_idx=last_instr_idx[: self.gen_params.fetch_width_log],
                        redirect=redirect,
                        unsafe=unsafe_stall,
                        block_prediction=predcheck_res.block_prediction,
                        empty_block=(fetch_mask == 0),
                    )

                    # Make sure this is called only once to avoid a huge mux on arguments
                    serializer.write(m, valid_mask=fetch_mask, slots=raw_instrs)
                with branch(flushing_counter != 0):
                    m.d.sync += flushing_counter.eq(flushing_counter - 1)

        @def_method(m, self.flush)
        def _():
            m.d.sync += flushing_counter.eq(req_counter.count_next)
            m.d.sync += prev_half_v.eq(0)

        return m


class Serializer(Elaboratable):
    """Many-to-one serializer

    Serializes many elements one-by-one in order and dispatches it to the consumer.
    The module accepts a new batch of elements only if the previous batch was fully
    consumed.

    It is a temporary workaround for a fetch buffer until the rest of the core becomes
    superscalar.
    """

    def __init__(self, width: int, elem_layout: MethodLayout) -> None:
        self.width = width
        self.elem_layout = elem_layout

        self.write = Method(
            i=[("valid_mask", self.width), ("slots", ArrayLayout(from_method_layout(self.elem_layout), self.width))]
        )
        self.read = Method(o=elem_layout)
        self.clean = Method()

        self.clean.add_conflict(self.write, Priority.LEFT)
        self.clean.add_conflict(self.read, Priority.LEFT)

    def elaborate(self, platform):
        m = TModule()

        m.submodules.prio_encoder = prio_encoder = PriorityEncoder(self.width)

        buffer = Array(Signal(from_method_layout(self.elem_layout)) for _ in range(self.width))
        valids = Signal(self.width)

        m.d.comb += prio_encoder.i.eq(valids)

        count = Signal(range(self.width + 1))
        m.d.comb += count.eq(popcount(valids))

        # To make sure, read can be called at the same time as write.
        self.read.schedule_before(self.write)

        @def_method(m, self.read, ready=~prio_encoder.n)
        def _():
            m.d.sync += valids.eq(valids & ~(1 << prio_encoder.o))
            return buffer[prio_encoder.o]

        @def_method(m, self.write, ready=prio_encoder.n | ((count == 1) & self.read.run))
        def _(valid_mask, slots):
            m.d.sync += valids.eq(valid_mask)

            for i in range(self.width):
                m.d.sync += buffer[i].eq(slots[i])

        @def_method(m, self.clean)
        def _():
            m.d.sync += valids.eq(0)

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
        def _(fb_addr, instr_block_cross, instr_valid, predecoded, block_prediction):
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
                        & ~block_prediction.branch_mask[i]
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
                if Extension.C in self.gen_params.isa.extensions:
                    return base - Mux(instr_block_cross & (idx == 0), 2, 0)
                return base

            # Target of a CFI that would redirect the frontend according to the prediction
            decoded_target_for_predicted_cfi = Signal(self.gen_params.isa.xlen)
            m.d.av_comb += decoded_target_for_predicted_cfi.eq(get_decoded_target_for(block_prediction.cfi_idx))

            # Target of a CFI that would redirect the frontend according to predecode info
            decoded_target_for_decoded_cfi = Signal(self.gen_params.isa.xlen)
            m.d.av_comb += decoded_target_for_decoded_cfi.eq(get_decoded_target_for(pd_redirect_idx))

            preceding_redirection = ~pd_redirection_enc.n & (
                ((CfiType.valid(block_prediction.cfi_type) & (pd_redirect_idx < block_prediction.cfi_idx)))
                | ~CfiType.valid(block_prediction.cfi_type)
            )

            mispredicted_cfi_type = CfiType.valid(block_prediction.cfi_type) & (
                block_prediction.cfi_type != decoded_cfi_types[block_prediction.cfi_idx]
            )

            mispredicted_cfi_target = (
                CfiType.is_branch(block_prediction.cfi_type) | CfiType.is_jal(block_prediction.cfi_type)
            ) & (
                ~block_prediction.maybe_cfi_target.valid
                | (decoded_target_for_predicted_cfi != block_prediction.maybe_cfi_target.value)
            )

            ret = Signal.like(self.check.data_out)
            m.d.av_comb += ret.block_prediction.eq(block_prediction)

            last_instr = Signal.like(block_prediction.cfi_idx)
            m.d.av_comb += last_instr.eq(
                Mux(CfiType.valid(block_prediction.cfi_type), block_prediction.cfi_idx, self.gen_params.fetch_width - 1)
            )

            with m.If(preceding_redirection | mispredicted_cfi_type):
                self.perf_preceding_redirection.incr(m, decoded_cfi_types[pd_redirect_idx], cond=preceding_redirection)
                self.perf_mispredicted_cfi_type.incr(m, block_prediction.cfi_type, cond=~preceding_redirection)
                m.d.av_comb += ret.mispredicted.eq(1)
                m.d.av_comb += last_instr.eq(
                    Mux(pd_redirection_enc.n, self.gen_params.fetch_width - 1, pd_redirect_idx)
                )
                m.d.av_comb += assign(
                    ret.block_prediction,
                    {
                        "cfi_idx": pd_redirect_idx,
                        "cfi_type": Mux(pd_redirection_enc.n, CfiType.INVALID, decoded_cfi_types[pd_redirect_idx]),
                        "maybe_cfi_target": {
                            "valid": ~CfiType.is_jalr(decoded_cfi_types[pd_redirect_idx]),
                            "value": decoded_target_for_decoded_cfi,
                        },
                    },
                )
            with m.Elif(mispredicted_cfi_target):
                self.perf_mispredicted_cfi_target.incr(m, block_prediction.cfi_type)
                m.d.av_comb += assign(
                    ret.block_prediction,
                    {
                        "maybe_cfi_target": {
                            "valid": 1,
                            "value": decoded_target_for_predicted_cfi,
                        },
                    },
                )

            m.d.av_comb += ret.block_prediction.branch_mask.eq(
                Cat([CfiType.is_branch(predecoded[i].cfi_type) for i in range(self.gen_params.fetch_width)])
                & instr_valid
                & ((1 << (last_instr + 1)) - 1)
            )

            return ret

        return m
