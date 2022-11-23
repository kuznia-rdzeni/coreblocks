from amaranth import *
from coreblocks.transactions import Method, def_method
from coreblocks.params import RSLayouts, GenParams, FuncUnitLayouts, Opcode, Funct3
from coreblocks.perip.wishbone import WishboneMaster
from coreblocks.utils import assign, AssignType

__all__ = ["LSUDummy"]

class LSUDummyInternals(Elaboratable):
    def __init__(self, gen_params: GenParams, bus: WishboneMaster,
                 currentInstr : Record, resultData : Record) -> None:
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

    def calculateAddr(self, m:Module):
        """
        Calculate Load/Store address as defined by RiscV spec
        """
        m.d.comb+=_addr.eq(self.currentInstr.s1_val+self.currentInstr.imm)

    def checkIfInstrReady(self, m : Module) -> Signal:
        """
        Check if we all values needed by instruction are already calculated.
        """
        s = Signal()
        m.d.comb+=s.eq(self.currentInstr.rp_s1==0 & self.currentInstr.rp_s2==0 & self.ready==0)
        return s

    def checkIfInstrIsLoad(self, m:Module) -> Signal:
        s = Signal()
        m.d.comb += s.eq(self.currentInstr.exec_fn.opcode==Opcode.LOAD)
        return s

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

        Methods:
        insert :
        Used to put instruction into reserved place.
        select:
        Used to reserve a place for intruction in LSU.
        update:
        Used to receive announcment that calculations of new value have ended
        and we have a value which can be used in father computations.
        get_result:
        To put load/store results to the next stage of pipeline
        exec_store:
        To execute store on retirement
        """
        self.gen_params = gen_params
        self.rs_layouts = gen_params.get(RSLayouts)
        self.fu_layouts = gen_params.get(FuncUnitLayouts)

        self.insert = Method(i=self.rs_layouts.insert_in)
        self.select = Method(o=self.rs_layouts.select_out)
        self.update = Method(i=self.rs_layouts.update_in)
        self.get_result = Method(o=self.fu_layouts.accept)
        self.exec_store = Method()

        self.bus=bus
        self.currentInstr = Record(self.rs_layouts.data_layout)
        self.resultData = Record(self.fu_layouts.accept)

    def elaborate(self, platform):
        m = Module()

        m.submodules.internals = intern = LSUDummyInternals(self.gen_params, self.bus, self.currentInstr, self.resultData)

        s_lsu_empty = Signal()
        m.d.comb+=s_lsu_empty.eq(self.currentInstr.rob_id==0)

        s_result_ready = intern.ready

        @def_method(m, self.select, s_lsu_empty)
        def _ (arg) -> Signal:
            """
            We always return 1, because we have only one place in
            instruction storage.
            """
            s = Signal()
            m.d.comb+=s.eq(1)
            return s

        @def_method(m, self.insert)
        def _(arg) ->Signal:
            m.d.sync+=self.currentInstr.eq(arg.rs_data)
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

        @def_method(m, self.exec_store, s_store_ready)
        def _(arg) -> Signal:
            pass
