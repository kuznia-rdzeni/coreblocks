from amaranth import *
from coreblocks.transactions import Method, def_method
from coreblocks.params import RSLayouts, GenParams, FuncUnitLayouts, Opcode, Funct3
from coreblocks.perip.wishbone import WishboneMaster
from coreblocks.utils import assign, AssignType

__all__ = ["LSUDummy"]

class LSUDummyInternals(Elaboratable):
    def __init__(self, gen_params: GenParams, bus: WishboneMaster,
                 currentInstr : Record, resultData : Record) -> None:
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

        Parameters
        ----------
        gen_params: GenParams
            Parameters to be used during processor generation.
        bus: WishboneMaster
            Instantion of wishbone master which should be used to communicate with
            data memory.
        currentInstr : Record
            Reference to signal which contain instruction, which is currently processed by LSU.
        resultData : Record
            Synchronous signall which contain data readed from memory.

        Attributes
        ----------
        result_ack : Signal
            Signal which should be set high by ``LSUDummy`` to inform ``LSUDummyInternals`` that
            we ended porcess instruction and all internal state should be cleared.
        result_ready : Signal
            Signal which is set high by ``LSUDummyInternals`` to inform ``LSUDummy`` that we have
            prepared data to be announced in the rest of core.
        _addr : Signal
            Internal signal which store combinatoricaly calculated address in memory.
        """
        self.gen_params = gen_params
        self.rs_layouts = gen_params.get(RSLayouts)
        self.currentInstr = currentInstr
        self.resultData = resultData
        self.bus=bus

        self.result_ack = Signal()
        self.result_ready = Signal()
        self._addr = Signal(self.gen_params.isa.xlen)

    def cleanCurrentInstr(self, m : Module):
        m.d.sync += self.result_ready.eq(0)
        m.d.sync += self.currentInstr.eq(0)
        m.d.sync += self.resultData.eq(0)

    def calculateAddr(self, m:Module):
        """ Calculate Load/Store address as defined by RiscV spec """
        m.d.comb+=self._addr.eq(self.currentInstr.s1_val+self.currentInstr.imm)

    def prepareBytesMask(self, m:Module) -> Signal:
        mask_len=self.gen_params.isa.xlen // self.bus.wb_params.granularity
        s = Signal(mask_len)
        with m.Switch(self.currentInstr.exec_fn.funct3):
            with m.Case(Funct3.B):
                m.d.comb+=s.eq(0x1)
            with m.Case(Funct3.H):
                m.d.comb+=s.eq(0x3)
            with m.case(Funct3.W):
                m.d.comb+=s.eq(0xf)
        return s


    def load_init(self, m:Module, s_load_initiated : Signal):
        self.calculateAddr(m)

        s_bytes_mask_to_read = self.prepareBytesMask(m)
        req = Record(self.bus.requestLayout)
        m.d.comb += req.addr.eq(self._addr)
        m.d.comb += req.we.eq(0)
        m.d.comb += req.sel.eq(s_bytes_mask_to_read)

        # load_init is under if so this transaction will request to be executed
        # after all uppers if will be taken, so there is no need to add here
        # additional signal as "request"
        with Transaction().body(m):
            self.bus.request(m, req)
            m.d.sync+=s_load_initiated.eq(1)

    def load_end(self, m : Module, s_load_initiated : Signal):
        with Transaction().body(m):
            fetched = self.bus.result(m)
            m.d.sync += s_load_initiated.eq(0)
            m.d.sync += self.result_ready.eq(1)
            with m.If(fetched.err == 0):
                m.d.sync += self.resultData.result.eq(fetched.data)
            with m.Else():
                m.d.sync += self.resultData.result.eq(0)
                #TODO Handle exception when it will be implemented

    def elaborate(self, platform):
        def checkIfInstrReady(self, m : Module) -> ValueLike:
            """Check if we all values needed by instruction are already calculated."""
            return (self.currentInstr.rp_s1==0) & (self.currentInstr.rp_s2==0) & (self.ready==0)
        def checkIfInstrIsLoad(self, m:Module) -> ValueLike:
            return self.currentInstr.exec_fn.opcode==Opcode.LOAD

        m = Module()
        
        s_instr_ready=self.checkIfInstrReady(m)
        s_instr_is_load = self.checkIfInstrIsLoad(m)
        s_load_initiated = Signal()

        with m.Switch(Cat([s_instr_ready,s_instr_is_load,s_load_initiated])):
            with m.Case("110"):
                self.load_init(m)
            with m.Case("111"):
                self.load_end(m)
            with m.Case():
                pass
                #TODO Implement store

        with m.If(self.ack):
            self.cleanCurrentInstr(m)
    

class LSUDummy(Elaboratable):
    def __init__(self, gen_params: GenParams, bus:WishboneMaster) -> None:
        """
        Very simple LSU, which serialize all stores and loads,
        to allow us work on a core as a whole. It isn't fully
        compliment to RiscV spec. Doesn't support checking if
        address is in correct range.

        It use the same interface as RS, because in future more
        inteligent LSU's will be connected without RS, so to
        have future proof module here also RS will be skipped
        and all RS operations will be handled inside of LSUDummy.

        Parameters
        ----------
        gen_params: GenParams
            Parameters to be used during processor generation.
        bus: WishboneMaster
            Instantion of wishbone master which should be used to communicate with
            data memory.

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
        currentInstr : Record
            Record which store currently pocessed instruction using RS data
            layout extended with ``valid`` bit.
        resultData : Record
            Record using ``FuncUnitLayouts.data`` shape which store temporarly
            results to be send to next pipeline step.
        """
        self.gen_params = gen_params
        self.rs_layouts = gen_params.get(RSLayouts)
        self.fu_layouts = gen_params.get(FuncUnitLayouts)

        self.insert = Method(i=self.rs_layouts.insert_in)
        self.select = Method(o=self.rs_layouts.select_out)
        self.update = Method(i=self.rs_layouts.update_in)
        self.get_result = Method(o=self.fu_layouts.accept)

        self.bus=bus
        self.currentInstr = Record(self.rs_layouts.data_layout+[("valid",1)])
        self.resultData = Record(self.fu_layouts.accept)

    def elaborate(self, platform):
        m = Module()

        m.submodules.internal = internal = LSUDummyInternals(self.gen_params, self.bus, self.currentInstr, self.resultData)

        s_result_ready = internal.ready

        @def_method(m, self.select, self.currentInstr.valid)
        def _ (arg) -> Signal:
            """
            We always return 1, because we have only one place in
            instruction storage.
            """
            return 1

        @def_method(m, self.insert)
        def _(arg) ->Signal:
            m.d.sync+=self.currentInstr.eq(arg.rs_data)
            m.d.sync+=self.currentInstr.valid.eq(1)
            m.d.sync+=assign(self.resultData, arg, AssignType.COMMON)

        @def_method(m, self.update)
        def _(arg) -> Signal:       
            with m.If(self.currentInstr.rp_s1==arg.tag):
                m.d.sync+=self.currentInstr.s1_val.eq(arg.value)
            with m.If(self.currentInstr.rp_s2==arg.tag):
                m.d.sync+=self.currentInstr.s2_val.eq(arg.value)

        @def_method(m, self.get_result, s_result_ready)
        def _(arg) -> Signal:
            m.d.comb += intern.result_ack.eq(1)
            return self.resultData
