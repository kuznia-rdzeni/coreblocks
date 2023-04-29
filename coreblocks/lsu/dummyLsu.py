from amaranth import *

from coreblocks.transactions import Method, def_method, Transaction, Priority
from coreblocks.params import *
from coreblocks.peripherals.wishbone import WishboneMaster
from coreblocks.utils import assign
from coreblocks.utils.protocols import FuncBlock


__all__ = ["LSUDummy", "LSUBlockComponent"]


class LSUDummyInternals(Elaboratable):
    """
    Internal implementation of `LSUDummy` logic, which should be embedded into `LSUDummy`
    class to expose transactional interface. After the instruction is processed,
    `result_ready` bit is set to 1.  `LSUDummy` is expected to put
    `result_ack` high for at least 1 cycle after the results have
    been read and can be cleared.

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
            An instance of the Wishbone master for interfacing with the data memory.
        current_instr : Record, in
            Reference to signal containing instruction currently processed by LSU.
        """
        self.gen_params = gen_params
        self.current_instr = current_instr
        self.bus = bus

        self.loadedData = Signal(self.gen_params.isa.xlen)
        self.get_result_ack = Signal()
        self.start_state = Signal()
        self.result_ready = Signal()
        self.execute_store = Signal()
        self.store_ready = Signal()
        self.clear = Signal()

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

    def op_init(self, m: Module, op_initiated: Signal, is_store: bool):
        addr = Signal(self.gen_params.isa.xlen)
        m.d.comb += addr.eq(self.calculate_addr())

        bytes_mask = self.prepare_bytes_mask(m, addr)
        req = Record(self.bus.requestLayout)
        m.d.comb += req.addr.eq(addr >> 2)  # calculate word address
        m.d.comb += req.we.eq(is_store)
        m.d.comb += req.sel.eq(bytes_mask)
        m.d.comb += req.data.eq(self.prepare_data_to_save(m, self.current_instr.s2_val, addr))

        # load_init is under an "if" so that this transaction requests to be executed
        # after all "if"s above are taken, so there is no need to add any additional
        # signal here as a "request"
        with Transaction().body(m):
            self.bus.request(m, req)
            m.d.sync += op_initiated.eq(1)

    def op_end(self, m: Module, op_initiated: Signal, is_store: bool):
        addr = Signal(self.gen_params.isa.xlen)
        m.d.comb += addr.eq(self.calculate_addr())

        with Transaction().body(m):
            fetched = self.bus.result(m)
            m.d.sync += op_initiated.eq(0)
            if is_store:
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
            return current_instr.exec_fn.op_type == OpType.LOAD

        m = Module()

        instr_ready = check_if_instr_ready(self.current_instr, self.result_ready)
        instr_is_load = check_if_instr_is_load(self.current_instr)
        op_initiated = Signal()

        with m.FSM("Start"):
            with m.State("Start"):
                m.d.comb += self.start_state.eq(1)
                with m.If(~self.clear & instr_ready & instr_is_load):
                    self.op_init(m, op_initiated, False)
                    m.next = "LoadInit"
                with m.If(~self.clear & instr_ready & ~instr_is_load):
                    m.d.sync += self.result_ready.eq(1)
                    m.next = "StoreWaitForExec"
            with m.State("LoadInit"):
                with m.If(~op_initiated):
                    with m.If(self.clear):
                        m.next = "Start"
                    with m.Else():
                        self.op_init(m, op_initiated, False)
                with m.Else():
                    with m.If(self.clear):
                        m.next = "LoadEndClear"
                    with m.Else():
                        m.next = "LoadEnd"
            with m.State("LoadEnd"):
                self.op_end(m, op_initiated, False)
                with m.If(self.get_result_ack | (self.clear & ~op_initiated)):
                    m.d.sync += self.result_ready.eq(0)
                    m.d.sync += self.loadedData.eq(0)
                    m.next = "Start"
                with m.If(self.clear & op_initiated):
                    m.d.sync += self.result_ready.eq(0)
                    m.next = "LoadEndClear"
            with m.State("LoadEndClear"):
                self.op_end(m, op_initiated, False)
                m.d.sync += self.result_ready.eq(0)
                with m.If(~op_initiated):
                    m.d.sync += self.loadedData.eq(0)
                    m.next = "Start"
            with m.State("StoreWaitForExec"):
                with m.If(self.get_result_ack):
                    m.d.sync += self.result_ready.eq(0)
                with m.If(self.execute_store):
                    self.op_init(m, op_initiated, True)
                    m.next = "StoreInit"
                with m.If(self.clear):
                    m.d.sync += self.result_ready.eq(0)
                    m.next = "Start"
            # don't handle clear in 'StoreInit' and 'StoreEnd' because in DummyLSU this states
            # are only reachable, when store is being commited. And commited instructions can not be cleared.
            with m.State("StoreInit"):
                with m.If(~op_initiated):
                    self.op_init(m, op_initiated, True)
                with m.Else():
                    m.next = "StoreEnd"
            with m.State("StoreEnd"):
                self.op_end(m, op_initiated, True)
                with m.If(self.store_ready):
                    m.d.sync += self.store_ready.eq(0)
                    m.next = "Start"
        return m


class LSUDummy(Elaboratable):
    """
    Very simple LSU, which serializes all stores and loads.
    It isn't fully compliant with RiscV spec. Doesn't support checking if
    address is in correct range. Addresses have to be aligned.

    It uses the same interface as RS.

    We assume that store cannot return an error.

    Attributes
    ----------
    select : Method
        Used to reserve a place for intruction in LSU.
    insert : Method
        Used to put instruction into a reserved place.
    update : Method
        Used to receive the announcement that calculations of a new value have ended
        and we have a value which can be used in further computations.
    get_result : Method
        To put load/store results to the next stage of pipeline.
    commit : Method
        Used to inform LSU that new instruction have been retired.
    clear : Method
        Used to clear LSU on interrupt.
    """

    optypes = {OpType.LOAD, OpType.STORE}

    def __init__(self, gen_params: GenParams, bus: WishboneMaster) -> None:
        """
        Parameters
        ----------
        gen_params : GenParams
            Parameters to be used during processor generation.
        bus : WishboneMaster
            An instance of the Wishbone master for interfacing with the data memory.
        """

        self.gen_params = gen_params
        self.fu_layouts = gen_params.get(FuncUnitLayouts)
        self.lsu_layouts = gen_params.get(LSULayouts)

        self.insert = Method(i=self.lsu_layouts.rs_insert_in)
        self.select = Method(o=self.lsu_layouts.rs_select_out)
        self.update = Method(i=self.lsu_layouts.rs_update_in)
        self.get_result = Method(o=self.fu_layouts.accept)
        self.commit = Method(i=self.lsu_layouts.commit)
        self.clear = Method()

        self.clear.add_conflict(self.insert, Priority.LEFT)
        self.clear.add_conflict(self.select, Priority.LEFT)
        self.clear.add_conflict(self.update, Priority.LEFT)
        self.clear.add_conflict(self.get_result, Priority.LEFT)
        self.clear.add_conflict(self.commit, Priority.LEFT)
        self.bus = bus

    def elaborate(self, platform):
        m = Module()
        reserved = Signal()  # means that current_instr is reserved
        current_instr = Record(self.lsu_layouts.rs_data_layout + [("valid", 1)])

        m.submodules.internal = internal = LSUDummyInternals(self.gen_params, self.bus, current_instr)

        result_ready = internal.result_ready

        @def_method(m, self.select, ~reserved & internal.start_state)
        def _():
            # We always return 0, because we have only one place in instruction storage.
            m.d.sync += reserved.eq(1)
            return {"rs_entry_id": 0}

        @def_method(m, self.insert)
        def _(rs_data: Record, rs_entry_id: Value):
            m.d.sync += assign(current_instr, rs_data)
            m.d.sync += current_instr.valid.eq(1)

        @def_method(m, self.update)
        def _(tag: Value, value: Value):
            with m.If(current_instr.rp_s1 == tag):
                m.d.sync += current_instr.s1_val.eq(value)
                m.d.sync += current_instr.rp_s1.eq(0)
            with m.If(current_instr.rp_s2 == tag):
                m.d.sync += current_instr.s2_val.eq(value)
                m.d.sync += current_instr.rp_s2.eq(0)

        #TODO fix, nie powinno się uruchamiać
        @def_method(m, self.get_result, result_ready)
        def _():
            m.d.comb += internal.get_result_ack.eq(1)
            with m.If(current_instr.exec_fn.op_type == OpType.LOAD):
                m.d.sync += current_instr.eq(0)
                m.d.sync += reserved.eq(0)
            return {"rob_id": current_instr.rob_id, "rp_dst": current_instr.rp_dst, "result": internal.loadedData}

        @def_method(m, self.commit)
        def _(rob_id: Value):
            with m.If((current_instr.exec_fn.op_type == OpType.STORE) & (rob_id == current_instr.rob_id)):
                m.d.sync += internal.execute_store.eq(1)

        @def_method(m, self.clear)
        def _():
            m.d.comb += internal.clear.eq(1)
            m.d.sync += current_instr.eq(0)
            m.d.sync += reserved.eq(0)

        with m.If(internal.store_ready):
            m.d.sync += internal.execute_store.eq(0)
            m.d.sync += current_instr.eq(0)
            m.d.sync += reserved.eq(0)

        return m


class LSUBlockComponent(BlockComponentParams):
    def get_module(self, gen_params: GenParams) -> FuncBlock:
        connections = gen_params.get(DependencyManager)
        wb_master = connections.get_dependency(WishboneDataKey())
        unit = LSUDummy(gen_params, wb_master)
        connections.add_dependency(InstructionCommitKey(), unit.commit)
        return unit

    def get_optypes(self) -> set[OpType]:
        return LSUDummy.optypes
