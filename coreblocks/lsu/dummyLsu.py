from amaranth import *
from coreblocks.transactions import Method, def_method, Transaction
from coreblocks.params import RSLayouts, GenParams, FuncUnitLayouts, Opcode, Funct3
from coreblocks.peripherals.wishbone import WishboneMaster
from coreblocks.utils import assign, AssignType, ValueLike

__all__ = ["LSUDummy"]


class LSUDummyInternals(Elaboratable):
    """
    Internal implementation of ``LSUDummy`` logic, which should be embedded into ``LSUDummy``
    class to expose transactional interface.

    ``LSUDummyInternals`` get reference to ``currentInstr`` so to a signal which
    is used as register in ``LSUDummy``. This signal contains instruction which is currently to be process.
    When instruction get all its arguments ``LSUDummyInternals`` automaticaly starts working
    (``LSUDummyInternals`` check in each cycle if instruction is ready). Based on content of
    ``currentInstr`` ``LSUDummyInternals`` make different actions. It can start load operation,
    by sending wichbone request to memory (of course using transactional framework) and
    next wait till memory sent response back. When response is received ``LSUDummyInternals``
    set ``result_ready`` bit to 1.

    It is expected, that ``LSUDummy`` will put ``result_ack`` high for minimum 1 cycle, when
    results and ``currentInstr`` aren't needed any more and should be cleared.

    Attributes
    ----------
    result_ack : Signal, in
        Signal which should be set high by ``LSUDummy`` to inform ``LSUDummyInternals`` that
        we ended porcess instruction and all internal state should be cleared.
    result_ready : Signal, out
        Signal which is set high by ``LSUDummyInternals`` to inform ``LSUDummy`` that we have
        prepared data to be announced in the rest of core.
    """

    def __init__(self, gen_params: GenParams, bus: WishboneMaster, currentInstr: Record, resultData: Record) -> None:
        """
        Parameters
        ----------
        gen_params: GenParams
            Parameters to be used during processor generation.
        bus: WishboneMaster
            Instantion of wishbone master which should be used to communicate with
            data memory.
        currentInstr : Record, in
            Reference to signal which contain instruction, which is currently processed by LSU.
        resultData : Record, out
            Synchronous signall which contain data readed from memory.
        """
        self.gen_params = gen_params
        self.rs_layouts = gen_params.get(RSLayouts)
        self.currentInstr = currentInstr
        self.resultData = resultData
        self.bus = bus

        self.result_ack = Signal()
        self.result_ready = Signal()

    def clean_current_instr(self, m: Module):
        m.d.sync += self.result_ready.eq(0)
        m.d.sync += self.resultData.eq(0)

    def calculate_addr(self):
        """Calculate Load/Store address as defined by RiscV spec"""
        return self.currentInstr.s1_val + self.currentInstr.imm

    def prepare_bytes_mask(self, m: Module) -> Signal:
        mask_len = self.gen_params.isa.xlen // self.bus.wb_params.granularity
        s = Signal(mask_len)
        with m.Switch(self.currentInstr.exec_fn.funct3):
            with m.Case(Funct3.B):
                m.d.comb += s.eq(0x1)
            with m.Case(Funct3.BU):
                m.d.comb += s.eq(0x1)
            with m.Case(Funct3.H):
                m.d.comb += s.eq(0x3)
            with m.Case(Funct3.HU):
                m.d.comb += s.eq(0x3)
            with m.Case(Funct3.W):
                m.d.comb += s.eq(0xF)
        return s

    def postprocess_load_data(self, m: Module, data: Signal):
        s = Signal.like(data)
        with m.Switch(self.currentInstr.exec_fn.funct3):
            with m.Case(Funct3.BU):
                m.d.comb += s.eq(Cat(data[:8], C(0, unsigned(s.shape().width - 8))))
            with m.Case(Funct3.HU):
                m.d.comb += s.eq(Cat(data[:16], C(0, unsigned(s.shape().width - 16))))
            with m.Case():
                m.d.comb += s.eq(data)
        return s

    def load_init(self, m: Module, s_load_initiated: Signal):
        addr = Signal(self.gen_params.isa.xlen)
        m.d.comb += addr.eq(self.calculate_addr())

        s_bytes_mask_to_read = self.prepare_bytes_mask(m)
        req = Record(self.bus.requestLayout)
        m.d.comb += req.addr.eq(addr)
        m.d.comb += req.we.eq(0)
        m.d.comb += req.sel.eq(s_bytes_mask_to_read)

        # load_init is under if so this transaction will request to be executed
        # after all uppers if will be taken, so there is no need to add here
        # additional signal as "request"
        with Transaction().body(m):
            self.bus.request(m, req)
            m.d.sync += s_load_initiated.eq(1)

    def load_end(self, m: Module, s_load_initiated: Signal):
        with Transaction().body(m):
            fetched = self.bus.result(m)
            m.d.sync += s_load_initiated.eq(0)
            m.d.sync += self.result_ready.eq(1)
            with m.If(fetched.err == 0):
                m.d.sync += self.resultData.result.eq(self.postprocess_load_data(m, fetched.data))
            with m.Else():
                m.d.sync += self.resultData.result.eq(0)
                # TODO Handle exception when it will be implemented

    def elaborate(self, platform):
        def check_if_instr_ready() -> ValueLike:
            """Check if we all values needed by instruction are already calculated."""
            return (
                (self.currentInstr.rp_s1 == 0)
                & (self.currentInstr.rp_s2 == 0)
                & (self.currentInstr.valid == 1)
                & (self.result_ready == 0)
            )

        def check_if_instr_is_load() -> ValueLike:
            return self.currentInstr.exec_fn.op_type == Opcode.LOAD

        m = Module()

        s_instr_ready = check_if_instr_ready()
        s_instr_is_load = check_if_instr_is_load()
        s_load_initiated = Signal()

        # We have to make reverse because bits in cases are in diffrent order than in Cat due to python indexing
        # of lists (from left to right) and ints (from right to left)
        INSTR_READY = 0b001
        INSTR_IS_LOAD = 0b010
        LOAD_INITIATED = 0b100
        with m.Switch(Cat(list(reversed([s_load_initiated, s_instr_is_load, s_instr_ready])))):
            with m.Case(INSTR_READY | INSTR_IS_LOAD):
                self.load_init(m, s_load_initiated)
            with m.Case(INSTR_READY | INSTR_IS_LOAD | LOAD_INITIATED):
                self.load_end(m, s_load_initiated)
            with m.Case():
                pass
                # TODO Implement store

        with m.If(self.result_ack):
            self.clean_current_instr(m)
        return m


class LSUDummy(Elaboratable):
    """
    Very simple LSU, which serialize all stores and loads,
    to allow us work on a core as a whole. It isn't fully
    compliment to RiscV spec. Doesn't support checking if
    address is in correct range.

    It use the same interface as RS, because in future more
    inteligent LSU's will be connected without RS, so to
    have future proof module here also RS will be skipped
    and all RS operations will be handled inside of LSUDummy.

    Attributes
    ----------
    select : Method
        Used to reserve a place for intruction in LSU.
    insert : Method
        Used to put instruction into reserved place.
    update : Method
        Used to receive announcment that calculations of new value have ended
        and we have a value which can be used in father computations.
    get_result : Method
        To put load/store results to the next stage of pipeline.
    """

    def __init__(self, gen_params: GenParams, bus: WishboneMaster) -> None:
        """
        Parameters
        ----------
        gen_params: GenParams
            Parameters to be used during processor generation.
        bus: WishboneMaster
            Instantion of wishbone master which should be used to communicate with
            data memory.
        """

        self.gen_params = gen_params
        self.rs_layouts = gen_params.get(RSLayouts)
        self.fu_layouts = gen_params.get(FuncUnitLayouts)

        self.insert = Method(i=self.rs_layouts.insert_in)
        self.select = Method(o=self.rs_layouts.select_out)
        self.update = Method(i=self.rs_layouts.update_in)
        self.get_result = Method(o=self.fu_layouts.accept)

        self.bus = bus

    def elaborate(self, platform):
        # currentInstr : Record
        #     Record which store currently pocessed instruction using RS data
        #     layout extended with ``valid`` bit.
        # resultData : Record
        #     Record using ``FuncUnitLayouts.data`` shape which store temporarly
        #     results to be send to next pipeline step.
        # reserved : Signal, out
        #     Register to mark, that ``currentInstr`` field is already reserved.
        m = Module()
        reserved = Signal()
        currentInstr = Record(self.rs_layouts.data_layout + [("valid", 1)])
        resultData = Record(self.fu_layouts.accept)

        m.submodules.internal = internal = LSUDummyInternals(self.gen_params, self.bus, currentInstr, resultData)

        s_result_ready = internal.result_ready

        @def_method(m, self.select, ~reserved)
        def _(arg):
            """
            We always return 1, because we have only one place in
            instruction storage.
            """
            m.d.sync += reserved.eq(1)
            return 1

        @def_method(m, self.insert, ~currentInstr.valid)
        def _(arg):
            m.d.sync += currentInstr.eq(arg.rs_data)
            m.d.sync += currentInstr.valid.eq(1)
            m.d.sync += assign(resultData, arg, fields=AssignType.COMMON)

        @def_method(m, self.update)
        def _(arg):
            with m.If(currentInstr.rp_s1 == arg.tag):
                m.d.sync += currentInstr.s1_val.eq(arg.value)
                m.d.sync += currentInstr.rp_s1.eq(0)
            with m.If(currentInstr.rp_s2 == arg.tag):
                m.d.sync += currentInstr.s2_val.eq(arg.value)
                m.d.sync += currentInstr.rp_s2.eq(0)

        @def_method(m, self.get_result, s_result_ready)
        def _(arg):
            m.d.comb += internal.result_ack.eq(1)
            m.d.sync += currentInstr.eq(0)
            m.d.sync += reserved.eq(0)
            return resultData

        return m
