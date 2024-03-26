from amaranth import *
from amaranth.utils import exact_log2
from amaranth.lib.coding import PriorityEncoder

from transactron.lib import BasicFifo, Semaphore, ConnectTrans, logging
from transactron.lib.metrics import *
from transactron.utils import MethodLayout, popcount
from transactron.utils.transactron_helpers import from_method_layout
from transactron import *

from coreblocks.cache.iface import CacheInterface
from coreblocks.frontend.decoder.rvc import InstrDecompress, is_instr_compressed

from coreblocks.params import *
from coreblocks.interface.layouts import *
from coreblocks.frontend.decoder.isa import *
from coreblocks.frontend.decoder.optypes import CfiType

log = logging.HardwareLogger("frontend.fetch")


class FetchUnit(Elaboratable):
    """
    Simple fetch unit. It has a PC inside and increments it by `isa.ilen_bytes`
    after each fetch.
    """

    def __init__(self, gen_params: GenParams, icache: CacheInterface, cont: Method) -> None:
        """
        Parameters
        ----------
        gen_params : GenParams
            Instance of GenParams with parameters which should be used to generate
            fetch unit.
        icache : CacheInterface
            Instruction Cache
        cont : Method
            Method which should be invoked to send fetched data to the next step.
            It has layout as described by `FetchLayout`.
        """
        self.gen_params = gen_params
        self.icache = icache
        self.cont = cont

        self.layouts = self.gen_params.get(FetchLayouts)

        self.resume = Method(i=self.layouts.resume)
        self.stall_exception = Method()
        # Fetch can be resumed to unstall from 'unsafe' instructions, and stalled because
        # of exception report, both can happen at any time during normal excecution.
        # ExceptionCauseRegister uses separate Transaction for it, so performace is not affected.
        self.stall_exception.add_conflict(self.resume, Priority.LEFT)

    def elaborate(self, platform):
        m = TModule()

        fetch_width = self.gen_params.fetch_width

        # Serializer is just a temporary workaround until we have a proper multiport FIFO
        # to which we can push bundles of instructions.
        m.submodules.serializer = serializer = Serializer(fetch_width, self.layouts.raw_instr)
        m.submodules.serializer_connector = ConnectTrans(serializer.read, self.cont)

        m.submodules.cache_requests = cache_requests = BasicFifo(layout=[("addr", self.gen_params.isa.xlen)], depth=2)

        # This limits number of fetch blocks the fetch unit can process
        # at a time. We start counting when sending a request to the cache and
        # stop when pushing a fetch packet out of the fetch unit.
        m.submodules.req_counter = req_counter = Semaphore(4)
        flushing_counter = Signal.like(req_counter.count)

        def flush():
            m.d.sync += flushing_counter.eq(req_counter.count_next)

        current_pc = Signal(self.gen_params.isa.xlen, reset=self.gen_params.start_pc)

        stalled_unsafe = Signal()
        stalled_exception = Signal()

        stalled = Signal()
        m.d.av_comb += stalled.eq(stalled_unsafe | stalled_exception)

        #
        # Fetch - stage 0
        # ================
        # - send a request to the instruction cache
        #
        with Transaction(name="Fetch_Stage0").body(m, request=~stalled):
            log.debug(m, True, "Sending request to cache for addr=0x{:x}", current_pc)
            req_counter.acquire(m)
            self.icache.issue_req(m, addr=current_pc)
            cache_requests.write(m, addr=current_pc)

            current_fetch_block = current_pc[self.gen_params.fetch_block_bytes_log :]

            # Assume we fallthrough to the next fetch block.
            m.d.sync += current_pc.eq(Cat(C(0, self.gen_params.fetch_block_bytes_log), current_fetch_block + 1))

        #
        # State passed between stage 1 and stage 2
        #
        m.submodules.s1_s2_pipe = s1_s2_pipe = Pipe(
            [
                ("fetch_block_addr", self.gen_params.isa.xlen),
                ("instr_valid", fetch_width),
                ("access_fault", 1),
                ("rvc", fetch_width),
                ("instr_block", self.gen_params.isa.ilen * fetch_width),
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
        prev_half_addr = Signal(self.gen_params.isa.xlen)
        prev_half_v = Signal()
        with Transaction(name="Fetch_Stage1").body(m):
            target = cache_requests.read(m)
            cache_resp = self.icache.accept_res(m)

            # The address of the first byte in the fetch block.
            fetch_block_addr = Cat(
                C(0, self.gen_params.fetch_block_bytes_log), target.addr[self.gen_params.fetch_block_bytes_log :]
            )
            # The index (in instructions) of the first instruction that we should process.
            fetch_block_offset = target.addr[
                exact_log2(self.gen_params.min_instr_width_bytes) : self.gen_params.fetch_block_bytes_log
            ]

            #
            # Expand compressed instructions from the fetch block.
            #
            expanded_instr = [Signal(self.gen_params.isa.ilen) for _ in range(fetch_width)]
            is_rvc = Signal(fetch_width)

            # Whether in this cycle we have a fetch block that contains
            # an instruction that crosses a fetch boundary
            instr_block_cross = Signal()
            m.d.av_comb += instr_block_cross.eq(
                prev_half_v
                & (
                    prev_half_addr[self.gen_params.fetch_block_bytes_log :] + 1
                    == fetch_block_addr[self.gen_params.fetch_block_bytes_log :]
                )
            )

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
                m.d.sync += prev_half_addr.eq(fetch_block_addr)
            else:
                valid_instr_mask = Cat(instr_start)

            log.debug(m, True, "[STAGE 1] half_valid: {}, half_addr: 0x{:x}", prev_half_v, prev_half_addr)
            log.debug(
                m,
                True,
                "[STAGE 1] pc=0x{:x}, fetch_block_addr=0x{:x} offset= {} fetch_block=0x{:x}",
                target.addr,
                fetch_block_addr,
                fetch_block_offset,
                cache_resp.fetch_block,
            )

            log.debug(
                m,
                True,
                "[STAGE 1] Valid instr: {:08b}, rvc_mask: {:08b}",
                valid_instr_mask,
                is_rvc,
            )

            s1_s2_pipe.write(
                m,
                fetch_block_addr=fetch_block_addr,
                instr_valid=valid_instr_mask,
                access_fault=cache_resp.error,
                rvc=is_rvc,
                instr_block=Cat(expanded_instr),
                instr_block_cross=instr_block_cross,
            )

        #
        # Fetch - stage 2
        # ================
        # - predecode instructions
        # - check if any of instructions redirects the frontend
        # - check if any of instructions stalls the frontend
        # - enqueue a packet of instructions
        predecoders = [Predecoder(self.gen_params) for _ in range(fetch_width)]
        for n, module in enumerate(predecoders):
            m.submodules[f"predecoder_{n}"] = module

        with Transaction(name="Fetch_Stage2").body(m):
            req_counter.release(m)
            s1_data = s1_s2_pipe.read(m)

            instrs = [s1_data.instr_block[i * 32 : (i + 1) * 32] for i in range(fetch_width)]
            fetch_block_addr = s1_data.fetch_block_addr
            instr_valid = s1_data.instr_valid
            access_fault = s1_data.access_fault

            log.debug(m, True, "[STAGE 2] instrs {:x} cross: {}", s1_data.instr_block, s1_data.instr_block_cross)

            # Predecode instructions
            for i in range(fetch_width):
                m.d.av_comb += predecoders[i].instr_in.eq(instrs[i])

            # Is the instruction unsafe (i.e. stalls the frontend until the backend resumes it).
            instr_unsafe = [Signal() for _ in range(fetch_width)]

            # Would that instruction redirect the fetch unit?
            instr_redirects = [Signal() for _ in range(fetch_width)]
            # If so, with what offset?
            redirection_offset = Array(Signal(signed(21)) for _ in range(fetch_width))

            for i in range(fetch_width):
                m.d.av_comb += redirection_offset[i].eq(predecoders[i].jump_offset)

                # Predict backward branches as taken
                m.d.av_comb += instr_redirects[i].eq(
                    (predecoders[i].cfi_type == CfiType.JAL)
                    | ((predecoders[i].cfi_type == CfiType.BRANCH) & (predecoders[i].jump_offset < 0))
                )

                # If there was an access fault, just mark every instruction as unsafe
                m.d.av_comb += instr_unsafe[i].eq(predecoders[i].is_unsafe | access_fault)

            m.submodules.prio_encoder = prio_encoder = PriorityEncoder(fetch_width)
            m.d.av_comb += prio_encoder.i.eq((Cat(instr_unsafe) | Cat(instr_redirects)) & instr_valid)

            redirect_or_unsafe_idx = prio_encoder.o
            redirect_or_unsafe = Signal()
            m.d.av_comb += redirect_or_unsafe.eq(~prio_encoder.n)

            redirect = Signal()
            m.d.av_comb += redirect.eq(redirect_or_unsafe & Array(instr_redirects)[redirect_or_unsafe_idx])

            unsafe_stall = Signal()
            m.d.av_comb += unsafe_stall.eq(redirect_or_unsafe & Array(instr_unsafe)[redirect_or_unsafe_idx])

            # This mask denotes what prefix of instructions we should enqueue.
            valid_instr_prefix = Signal(fetch_width)
            with m.If(redirect_or_unsafe):
                # If there is an instruction that redirects or stalls the frontend, enqueue
                # instructions only up to that instruction.
                m.d.av_comb += valid_instr_prefix.eq((1 << (redirect_or_unsafe_idx + 1)) - 1)
            with m.Else():
                m.d.av_comb += valid_instr_prefix.eq(C(1).replicate(fetch_width))

            log.info(
                m,
                True,
                "[STAGE 2] Valid mask: {:08b} redirection mask: {:08b} jump_offset: {}",
                instr_valid,
                Cat(instr_redirects),
                predecoders[0].jump_offset,
            )

            # The ultimate mask that tells which instructions should be sent to the backend.
            fetch_mask = Signal(fetch_width)
            m.d.av_comb += fetch_mask.eq(instr_valid & valid_instr_prefix)

            # If the frontend needs to be redirected, to which PC?
            redirection_instr_pc = Signal(self.gen_params.isa.xlen)
            m.d.av_comb += redirection_instr_pc.eq(
                fetch_block_addr | (redirect_or_unsafe_idx << exact_log2(self.gen_params.min_instr_width_bytes))
            )

            if Extension.C in self.gen_params.isa.extensions:
                # Special case - the first instruction may have a different pc due to
                # a fetch boundary crossing.
                with m.If(s1_data.instr_block_cross & (redirect_or_unsafe_idx == 0)):
                    m.d.av_comb += redirection_instr_pc.eq(fetch_block_addr - 2)

            # Aggregate all signals that will be sent out of the fetch unit.
            raw_instrs = [Signal(self.layouts.raw_instr) for _ in range(fetch_width)]
            for i in range(fetch_width):
                m.d.av_comb += [
                    raw_instrs[i].instr.eq(instrs[i]),
                    raw_instrs[i].pc.eq(fetch_block_addr | (i << exact_log2(self.gen_params.min_instr_width_bytes))),
                    raw_instrs[i].access_fault.eq(access_fault),
                    raw_instrs[i].rvc.eq(s1_data.rvc[i]),
                    raw_instrs[i].predicted_taken.eq(instr_redirects[i]),
                ]

            if Extension.C in self.gen_params.isa.extensions:
                with m.If(s1_data.instr_block_cross):
                    m.d.av_comb += raw_instrs[0].pc.eq(fetch_block_addr - 2)

            with m.If(flushing_counter == 0):
                with m.If(access_fault | unsafe_stall):
                    # TODO: Raise different code for page fault when supported
                    flush()
                    m.d.sync += stalled_unsafe.eq(1)
                with m.Elif(redirect):
                    new_pc = Signal.like(current_pc)
                    m.d.av_comb += new_pc.eq(redirection_instr_pc + redirection_offset[redirect_or_unsafe_idx])

                    log.debug(m, True, "Fetch redirected to pc 0x{:x}. Flushing...", new_pc)
                    flush()
                    m.d.sync += current_pc.eq(new_pc)

                slots = {f"slot_{i}": raw_instrs[i] for i in range(fetch_width)}
                # Make sure this is called only once to avoid a huge mux on arguments
                serializer.write(m, valid_mask=fetch_mask, **slots)
            with m.Else():
                m.d.sync += flushing_counter.eq(flushing_counter - 1)

        @def_method(m, self.resume, ready=(stalled & (flushing_counter == 0)))
        def _(pc: Value, resume_from_exception: Value):
            log.info(m, True, "Resuming from exception new_pc=0x{:x}", pc)
            m.d.sync += current_pc.eq(pc)
            m.d.sync += stalled_unsafe.eq(0)
            with m.If(resume_from_exception):
                m.d.sync += stalled_exception.eq(0)

        @def_method(m, self.stall_exception)
        def _():
            log.info(m, True, "Stalling the fetch unit because of an exception")
            serializer.clean(m)
            m.d.sync += stalled_exception.eq(1)
            flush()

        return m


class Pipe(Elaboratable):
    """
    This module implements a `Pipe`. It is a halfway between
    `Forwarder` and `2-FIFO`. In the `Pipe` data is always
    stored localy, so the critical path of the data is cut, but there is a
    combinational path between the control signals of the `read` and
    the `write` methods. For comparison:
    - in `Forwarder` there is both a data and a control combinational path
    - in `2-FIFO` there are no combinational paths

    The `read` method is scheduled before the `write`.

    Attributes
    ----------
    read: Method
        The read method. Accepts an empty argument, returns a `Record`.
    write: Method
        The write method. Accepts a `Record`, returns empty result.
    """

    def __init__(self, layout: MethodLayout):
        """
        Parameters
        ----------
        layout: record layout
            The format of records forwarded.
        """
        self.read = Method(o=layout)
        self.write = Method(i=layout)
        self.clear = Method()
        self.head = Signal.like(self.read.data_out)

        self.clear.add_conflict(self.read, Priority.LEFT)
        self.clear.add_conflict(self.write, Priority.LEFT)

    def elaborate(self, platform):
        m = TModule()

        reg = Signal.like(self.read.data_out)
        reg_valid = Signal()
        m.d.top_comb += self.head.eq(reg)

        self.read.schedule_before(self.write)  # to avoid combinational loops

        @def_method(m, self.read, ready=reg_valid)
        def _():
            m.d.sync += reg_valid.eq(0)
            return reg

        @def_method(m, self.write, ready=~reg_valid | self.read.run)
        def _(arg):
            m.d.sync += reg.eq(arg)
            m.d.sync += reg_valid.eq(1)

        @def_method(m, self.clear)
        def _():
            m.d.sync += reg_valid.eq(0)

        return m


class Serializer(Elaboratable):
    def __init__(self, width: int, layout: MethodLayout) -> None:
        self.width = width
        self.layout = layout

        self.write = Method(
            i=[("valid_mask", self.width)] + [(f"slot_{i}", from_method_layout(self.layout)) for i in range(self.width)]
        )
        self.read = Method(o=layout)
        self.clean = Method()

        self.clean.add_conflict(self.write, Priority.LEFT)
        self.clean.add_conflict(self.read, Priority.LEFT)

    def elaborate(self, platform):
        m = TModule()

        m.submodules.prio_encoder = prio_encoder = PriorityEncoder(self.width)

        buffer = Array(Signal(from_method_layout(self.layout)) for _ in range(self.width))
        valids = Signal(self.width)

        m.d.comb += prio_encoder.i.eq(valids)

        count = Signal(range(self.width + 1))
        m.d.comb += count.eq(popcount(valids))

        # To make sure, read can be called at the same time as write.
        self.read.schedule_before(self.write)

        @def_method(m, self.read, ready=~prio_encoder.n)
        def _():
            m.d.sync += valids.eq(valids & ~(1 << prio_encoder.o))
            log.info(
                m, True, "Pushing out pc=0x{:x} instr=0x{:x}", buffer[prio_encoder.o].pc, buffer[prio_encoder.o].instr
            )
            return buffer[prio_encoder.o]

        @def_method(m, self.write, ready=prio_encoder.n | ((count == 1) & self.read.run))
        def _(**kwargs):
            log.info(m, True, "Serializing, mask: {:08b}", kwargs["valid_mask"])
            m.d.sync += valids.eq(kwargs["valid_mask"])

            for i in range(self.width):
                m.d.sync += buffer[i].eq(kwargs[f"slot_{i}"])

        @def_method(m, self.clean)
        def _():
            m.d.sync += valids.eq(0)

        return m


class Predecoder(Elaboratable):
    def __init__(self, gen_params: GenParams) -> None:
        """
        Parameters
        ----------
        gen_params: GenParams
            Core generation parameters.
        """
        self.gen_params = gen_params

        #
        # Input ports
        #

        self.instr_in = Signal(self.gen_params.isa.xlen)

        #
        # Output ports
        #
        self.cfi_type = Signal(CfiType)
        self.jump_offset = Signal(signed(21))

        self.is_unsafe = Signal()

    def elaborate(self, platform):
        m = TModule()

        opcode = self.instr_in[2:7]

        bimm = Signal(signed(13))
        jimm = Signal(signed(21))
        iimm = Signal(signed(12))

        m.d.comb += [
            iimm.eq(self.instr_in[20:]),
            bimm.eq(Cat(0, self.instr_in[8:12], self.instr_in[25:31], self.instr_in[7], self.instr_in[31])),
            jimm.eq(Cat(0, self.instr_in[21:31], self.instr_in[20], self.instr_in[12:20], self.instr_in[31])),
        ]

        with m.Switch(opcode):
            with m.Case(Opcode.BRANCH):
                m.d.comb += self.cfi_type.eq(CfiType.BRANCH)
                m.d.comb += self.jump_offset.eq(bimm)
            with m.Case(Opcode.JAL):
                m.d.comb += self.cfi_type.eq(CfiType.JAL)
                m.d.comb += self.jump_offset.eq(jimm)
            with m.Case(Opcode.JALR):
                m.d.comb += self.cfi_type.eq(CfiType.JALR)
                m.d.comb += self.jump_offset.eq(iimm)
            with m.Default():
                m.d.comb += self.cfi_type.eq(CfiType.INVALID)

        m.d.comb += self.is_unsafe.eq(opcode == Opcode.SYSTEM)

        return m
