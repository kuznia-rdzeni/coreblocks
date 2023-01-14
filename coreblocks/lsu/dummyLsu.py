from amaranth import *
from coreblocks.transactions import Method, def_method, Transaction
from coreblocks.params import RSLayouts, GenParams, FuncUnitLayouts, Opcode, Funct3, LSULayouts
from coreblocks.peripherals.wishbone import WishboneMaster

__all__ = ["LSUDummy"]


class LSUDummyInternals(Elaboratable):
    """
    Internal implementation of `LSUDummy` logic, which should be embedded into `LSUDummy`
    class to expose transactional interface. After the instruction is processed,
    `result_ready` bit is set to 1. It is expected, that `LSUDummy` will put
    `result_ack` high for minimum 1 cycle, when the results and `current_instr` aren't
    needed anymore and should be cleared.

    Attributes
    ----------
    get_result_ack : Signal, in
        Instructs to clean the internal state after processing an instruction.
    result_ready : Signal, out
        Signals that `resultData` is valid.
    """

    def __init__(self, gen_params: GenParams, bus: WishboneMaster, current_instr: Record) -> None:
        """
        Parameters
        ----------
        gen_params : GenParams
            Parameters to be used during processor generation.
        bus : WishboneMaster
            Instantion of wishbone master which should be used to communicate with
            data memory.
        current_instr : Record, in
            Reference to signal containing instruction currently processed by LSU.
        """
        self.gen_params = gen_params
        self.rs_layouts = gen_params.get(RSLayouts)
        self.current_instr = current_instr
        self.bus = bus

        self.loadedData = Signal(self.gen_params.isa.xlen)
        self.get_result_ack = Signal()
        self.result_ready = Signal()
        self.execute_store = Signal()
        self.store_ready = Signal()
        self.ready_for_store = Signal()

    def calculate_addr(self):
        """Calculate Load/Store address as defined by RiscV spec"""
        return self.current_instr.s1_val + self.current_instr.imm

    def prepare_bytes_mask(self, m: Module, addr: Signal) -> Signal:
        mask_len = self.gen_params.isa.xlen // self.bus.wb_params.granularity
        mask = Signal(mask_len)
        with m.Switch(self.current_instr.exec_fn.funct3):
            with m.Case(Funct3.B, Funct3.BU):
                m.d.comb += mask.eq(0x1 << addr[0:2])
            with m.Case(Funct3.H, Funct3.HU):
                m.d.comb += mask.eq(0x3 << (addr[1] << 1))
            with m.Case(Funct3.W):
                m.d.comb += mask.eq(0xF)
        return mask

    def postprocess_load_data(self, m: Module, raw_data: Signal, addr: Signal):
        data = Signal.like(raw_data)
        with m.Switch(self.current_instr.exec_fn.funct3):
            with m.Case(Funct3.B, Funct3.BU):
                tmp = Signal(8)
                m.d.comb += tmp.eq((raw_data >> (addr[0:2] << 3)) & 0xFF)
                with m.If(self.current_instr.exec_fn.funct3 == Funct3.B):
                    m.d.comb += data.eq(tmp.as_signed())
                with m.Else():
                    m.d.comb += data.eq(tmp)
            with m.Case(Funct3.H, Funct3.HU):
                tmp = Signal(16)
                m.d.comb += tmp.eq((raw_data >> (addr[1] << 4)) & 0xFFFF)
                with m.If(self.current_instr.exec_fn.funct3 == Funct3.H):
                    m.d.comb += data.eq(tmp.as_signed())
                with m.Else():
                    m.d.comb += data.eq(tmp)
            with m.Case():
                m.d.comb += data.eq(raw_data)
        return data

    def prepare_data_to_save(self, m: Module, raw_data: Signal, addr: Signal):
        data = Signal.like(raw_data)
        with m.Switch(self.current_instr.exec_fn.funct3):
            with m.Case(Funct3.B):
                m.d.comb += data.eq(raw_data[0:8] << (addr[0:2] << 3))
            with m.Case(Funct3.H):
                m.d.comb += data.eq(raw_data[0:16] << (addr[1] << 4))
            with m.Case():
                m.d.comb += data.eq(raw_data)
        return data

    def op_init(self, m: Module, op_initiated: Signal, we: int):
        addr = Signal(self.gen_params.isa.xlen)
        m.d.comb += addr.eq(self.calculate_addr())

        bytes_mask = self.prepare_bytes_mask(m, addr)
        req = Record(self.bus.requestLayout)
        # make address aligned to 4
        m.d.comb += req.addr.eq(addr & ~0x3)
        m.d.comb += req.we.eq(we)
        m.d.comb += req.sel.eq(bytes_mask)
        if we:
            m.d.comb += req.data.eq(self.prepare_data_to_save(m, self.current_instr.s2_val, addr))

        # load_init is under "if" so this transaction will request to be executed
        # after all uppers "if" will be taken, so there is no need to add here
        # additional signal as "request"
        with Transaction().body(m):
            self.bus.request(m, req)
            m.d.sync += op_initiated.eq(1)

    def op_end(self, m: Module, op_initiated: Signal, if_store: bool):
        addr = Signal(self.gen_params.isa.xlen)
        m.d.comb += addr.eq(self.calculate_addr())

        with Transaction().body(m):
            fetched = self.bus.result(m)
            m.d.sync += op_initiated.eq(0)
            if if_store:
                m.d.sync += self.store_ready.eq(1)
            else:
                m.d.sync += self.result_ready.eq(1)
                with m.If(fetched.err == 0):
                    m.d.sync += self.loadedData.eq(self.postprocess_load_data(m, fetched.data, addr))
                with m.Else():
                    m.d.sync += self.loadedData.eq(0)

    def elaborate(self, platform):
        def check_if_instr_ready(current_instr: Record, result_ready: Signal) -> Value:
            """Check if all values needed by instruction are already calculated."""
            return (
                (current_instr.rp_s1 == 0)
                & (current_instr.rp_s2 == 0)
                & (current_instr.valid == 1)
                & (result_ready == 0)
            )

        def check_if_instr_is_load(current_instr: Record) -> Value:
            return current_instr.exec_fn.op_type == Opcode.LOAD

        m = Module()

        instr_ready = check_if_instr_ready(self.current_instr, self.result_ready)
        instr_is_load = check_if_instr_is_load(self.current_instr)
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
    Very simple LSU, which serializes all stores and loads,
    It isn't fully compliant with RiscV spec. Doesn't support checking if
    address is in correct range. Addresses have to be aligned.

    It use the same interface as RS.

    We assume that store can not return error.

    Attributes
    ----------
    select : Method
        Used to reserve a place for intruction in LSU.
    insert : Method
        Used to put instruction into reserved place.
    update : Method
        Used to receive the announcement that calculations of a new value have ended
        and we have a value which can be used in further computations.
    get_result : Method
        To put load/store results to the next stage of pipeline.
    """

    def __init__(self, gen_params: GenParams, bus: WishboneMaster) -> None:
        """
        Parameters
        ----------
        gen_params : GenParams
            Parameters to be used during processor generation.
        bus : WishboneMaster
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
        # current_instr : Record
        #     Record which store currently pocessed instruction using RS data
        #     layout extended with ``valid`` bit.
        # reserved : Signal, out
        #     Register to mark, that ``current_instr`` field is already reserved.
        m = Module()
        reserved = Signal()
        current_instr = Record(self.rs_layouts.data_layout + [("valid", 1)])

        m.submodules.internal = internal = LSUDummyInternals(self.gen_params, self.bus, current_instr)

        result_ready = internal.result_ready

        @def_method(m, self.select, ~reserved)
        def _(arg):
            # We always return 0, because we have only one place in instruction storage.
            m.d.sync += reserved.eq(0)
            return 0

        @def_method(m, self.insert, ~current_instr.valid)
        def _(arg):
            m.d.sync += current_instr.eq(arg.rs_data)
            m.d.sync += current_instr.valid.eq(1)

        @def_method(m, self.update)
        def _(arg):
            with m.If(current_instr.rp_s1 == arg.tag):
                m.d.sync += current_instr.s1_val.eq(arg.value)
                m.d.sync += current_instr.rp_s1.eq(0)
            with m.If(current_instr.rp_s2 == arg.tag):
                m.d.sync += current_instr.s2_val.eq(arg.value)
                m.d.sync += current_instr.rp_s2.eq(0)

        @def_method(m, self.get_result, result_ready)
        def _(arg):
            m.d.comb += internal.get_result_ack.eq(1)
            with m.If(current_instr.exec_fn.op_type == Opcode.LOAD):
                m.d.sync += current_instr.eq(0)
                m.d.sync += reserved.eq(0)
            return {"rob_id": current_instr.rob_id, "rp_dst": current_instr.rp_dst, "result": internal.loadedData}

        @def_method(m, self.commit, internal.ready_for_store)
        def _(arg):
            with m.If((current_instr.exec_fn.op_type == Opcode.STORE) & (arg.rob_id == current_instr.rob_id)):
                m.d.sync += internal.execute_store.eq(1)

        with m.If(internal.store_ready):
            m.d.sync += internal.execute_store.eq(0)
            m.d.sync += current_instr.eq(0)
            m.d.sync += reserved.eq(0)

        return m
