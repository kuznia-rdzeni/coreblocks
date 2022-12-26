from amaranth import *
from coreblocks.transactions import Method, def_method, Transaction
from coreblocks.params import RSLayouts, GenParams, FuncUnitLayouts, Opcode, Funct3, LSULayouts
from coreblocks.peripherals.wishbone import WishboneMaster

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
    get_result_ack : Signal, in
        Signal which should be set high by ``LSUDummy`` to inform ``LSUDummyInternals`` that
        we pushed result to next pipeline stage and depends from instruction type some state can be freed.
    result_ready : Signal, out
        Signal which is set high by ``LSUDummyInternals`` to inform ``LSUDummy`` that we have
        prepared data to be announced in the rest of core.
    """

    def __init__(self, gen_params: GenParams, bus: WishboneMaster, currentInstr: Record) -> None:
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
        """
        self.gen_params = gen_params
        self.rs_layouts = gen_params.get(RSLayouts)
        self.currentInstr = currentInstr
        self.bus = bus

        self.loadedData = Signal(self.gen_params.isa.xlen)
        self.get_result_ack = Signal()
        self.result_ready = Signal()
        self.execute_store = Signal()
        self.store_ready = Signal()
        self.ready_for_store = Signal()

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

    def op_init(self, m: Module, op_initiated: Signal, we: int):
        addr = Signal(self.gen_params.isa.xlen)
        m.d.comb += addr.eq(self.calculate_addr())

        bytes_mask = self.prepare_bytes_mask(m)
        req = Record(self.bus.requestLayout)
        m.d.comb += req.addr.eq(addr)
        m.d.comb += req.we.eq(we)
        m.d.comb += req.sel.eq(bytes_mask)
        if we:
            m.d.comb += req.data.eq(self.currentInstr.s2_val)

        # load_init is under if so this transaction will request to be executed
        # after all uppers if will be taken, so there is no need to add here
        # additional signal as "request"
        with Transaction().body(m):
            self.bus.request(m, req)
            m.d.sync += op_initiated.eq(1)

    def op_end(self, m: Module, op_initiated: Signal, if_store: bool):
        with Transaction().body(m):
            fetched = self.bus.result(m)
            m.d.sync += op_initiated.eq(0)
            if if_store:
                m.d.sync += self.store_ready.eq(1)
            else:
                m.d.sync += self.result_ready.eq(1)
                with m.If(fetched.err == 0):
                    m.d.sync += self.loadedData.eq(self.postprocess_load_data(m, fetched.data))
                with m.Else():
                    m.d.sync += self.loadedData.eq(0)

    def elaborate(self, platform):
        def check_if_instr_ready() -> Value:
            """Check if we all values needed by instruction are already calculated."""
            return (
                (self.currentInstr.rp_s1 == 0)
                & (self.currentInstr.rp_s2 == 0)
                & (self.currentInstr.valid == 1)
                & (self.result_ready == 0)
            )

        def check_if_instr_is_load() -> Value:
            return self.currentInstr.exec_fn.op_type == Opcode.LOAD

        m = Module()

        instr_ready = check_if_instr_ready()
        instr_is_load = check_if_instr_is_load()
        op_initiated = Signal()

        with m.FSM("Start"):
            with m.State("Start"):
                with m.If(instr_ready & instr_is_load):
                    self.op_init(m, op_initiated, 0)
                    m.next = "LoadInit"
                with m.If(instr_ready & ~instr_is_load):
                    m.d.sync += self.result_ready.eq(1)
                    m.d.sync += self.ready_for_store.eq(1)
                    m.next = "StoreWaitForExec"
            with m.State("LoadInit"):
                with m.If(~op_initiated):
                    self.op_init(m, op_initiated, 0)
                with m.Else():
                    m.next = "LoadEnd"
            with m.State("LoadEnd"):
                self.op_end(m, op_initiated, False)
                with m.If(self.get_result_ack):
                    m.d.sync += self.result_ready.eq(0)
                    m.d.sync += self.loadedData.eq(0)
                    m.next = "Start"
            with m.State("StoreWaitForExec"):
                with m.If(self.get_result_ack):
                    m.d.sync += self.result_ready.eq(0)
                with m.If(self.execute_store):
                    self.op_init(m, op_initiated, 1)
                    m.next = "StoreInit"
            with m.State("StoreInit"):
                with m.If(~op_initiated):
                    self.op_init(m, op_initiated, 1)
                with m.Else():
                    m.next = "StoreEnd"
            with m.State("StoreEnd"):
                self.op_end(m, op_initiated, True)
                with m.If(self.store_ready):
                    m.d.sync += self.store_ready.eq(0)
                    m.d.sync += self.ready_for_store.eq(0)
                    m.next = "Start"
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

    We assume that store can not return error.

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
        self.lsu_layouts = gen_params.get(LSULayouts)

        self.insert = Method(i=self.rs_layouts.insert_in)
        self.select = Method(o=self.rs_layouts.select_out)
        self.update = Method(i=self.rs_layouts.update_in)
        self.get_result = Method(o=self.fu_layouts.accept)
        self.commit = Method(i=self.lsu_layouts.commit)

        self.bus = bus

    def elaborate(self, platform):
        # currentInstr : Record
        #     Record which store currently pocessed instruction using RS data
        #     layout extended with ``valid`` bit.
        # reserved : Signal, out
        #     Register to mark, that ``currentInstr`` field is already reserved.
        m = Module()
        reserved = Signal()
        currentInstr = Record(self.rs_layouts.data_layout + [("valid", 1)])

        m.submodules.internal = internal = LSUDummyInternals(self.gen_params, self.bus, currentInstr)

        result_ready = internal.result_ready

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

        @def_method(m, self.update)
        def _(arg):
            with m.If(currentInstr.rp_s1 == arg.tag):
                m.d.sync += currentInstr.s1_val.eq(arg.value)
                m.d.sync += currentInstr.rp_s1.eq(0)
            with m.If(currentInstr.rp_s2 == arg.tag):
                m.d.sync += currentInstr.s2_val.eq(arg.value)
                m.d.sync += currentInstr.rp_s2.eq(0)

        @def_method(m, self.get_result, result_ready)
        def _(arg):
            m.d.comb += internal.get_result_ack.eq(1)
            with m.If(currentInstr.exec_fn.op_type == Opcode.LOAD):
                m.d.sync += currentInstr.eq(0)
                m.d.sync += reserved.eq(0)
            return {"rob_id": currentInstr.rob_id, "rp_dst": currentInstr.rp_dst, "result": internal.loadedData}

        @def_method(m, self.commit, internal.ready_for_store)
        def _(arg):
            with m.If((currentInstr.exec_fn.op_type == Opcode.STORE) & (arg.rob_id == currentInstr.rob_id)):
                m.d.sync += internal.execute_store.eq(1)

        with m.If(internal.store_ready):
            m.d.sync += internal.execute_store.eq(0)
            m.d.sync += currentInstr.eq(0)
            m.d.sync += reserved.eq(0)

        return m
