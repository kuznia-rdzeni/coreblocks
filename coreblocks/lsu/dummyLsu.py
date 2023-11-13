from amaranth import *

from transactron import Method, def_method, Transaction, TModule
from transactron.core import Priority
from coreblocks.params import *
from coreblocks.peripherals.wishbone import WishboneMaster
from coreblocks.utils import assign, ModuleLike
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

        self.dependency_manager = self.gen_params.get(DependencyManager)
        self.report = self.dependency_manager.get_dependency(ExceptionReportKey())

        self.loadedData = Signal(self.gen_params.isa.xlen)
        self.get_result_ack = Signal()
        self.result_ready = Signal()
        self.execute = Signal()
        self.op_exception = Signal()

    def calculate_addr(self, m: ModuleLike):
        addr = Signal(self.gen_params.isa.xlen)
        m.d.comb += addr.eq(self.current_instr.s1_val + self.current_instr.imm)
        return addr

    def prepare_bytes_mask(self, m: ModuleLike, addr: Signal) -> Signal:
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

    def postprocess_load_data(self, m: ModuleLike, raw_data: Signal, addr: Signal):
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

    def prepare_data_to_save(self, m: ModuleLike, raw_data: Signal, addr: Signal):
        data = Signal.like(raw_data)
        with m.Switch(self.current_instr.exec_fn.funct3):
            with m.Case(Funct3.B):
                m.d.comb += data.eq(raw_data[0:8] << (addr[0:2] << 3))
            with m.Case(Funct3.H):
                m.d.comb += data.eq(raw_data[0:16] << (addr[1] << 4))
            with m.Case():
                m.d.comb += data.eq(raw_data)
        return data

    def check_align(self, m: TModule, addr: Signal):
        aligned = Signal()
        with m.Switch(self.current_instr.exec_fn.funct3):
            with m.Case(Funct3.W):
                m.d.comb += aligned.eq(addr[0:2] == 0)
            with m.Case(Funct3.H, Funct3.HU):
                m.d.comb += aligned.eq(addr[0] == 0)
            with m.Case():
                m.d.comb += aligned.eq(1)
        return aligned

    def elaborate(self, platform):
        m = TModule()

        instr_ready = (
            (self.current_instr.rp_s1 == 0)
            & (self.current_instr.rp_s2 == 0)
            & self.current_instr.valid
            & ~self.result_ready
        )

        is_load = self.current_instr.exec_fn.op_type == OpType.LOAD

        addr = self.calculate_addr(m)
        aligned = self.check_align(m, addr)
        bytes_mask = self.prepare_bytes_mask(m, addr)
        data = self.prepare_data_to_save(m, self.current_instr.s2_val, addr)

        with m.FSM("Start"):
            with m.State("Start"):
                with m.If(instr_ready & (self.execute | is_load)):
                    with m.If(aligned):
                        with Transaction().body(m):
                            self.bus.request(m, addr=addr >> 2, we=~is_load, sel=bytes_mask, data=data)
                            m.next = "End"
                    with m.Else():
                        with Transaction().body(m):
                            m.d.sync += self.op_exception.eq(1)
                            m.d.sync += self.result_ready.eq(1)

                            cause = Mux(
                                is_load, ExceptionCause.LOAD_ADDRESS_MISALIGNED, ExceptionCause.STORE_ADDRESS_MISALIGNED
                            )
                            self.report(m, rob_id=self.current_instr.rob_id, cause=cause)

                            m.next = "End"

            with m.State("End"):
                with Transaction().body(m):
                    fetched = self.bus.result(m)

                    m.d.sync += self.loadedData.eq(self.postprocess_load_data(m, fetched.data, addr))

                    # no clear (synonymous with instruction valid signal) was asserted
                    with m.If(self.current_instr.valid):
                        with m.If(fetched.err):
                            cause = Mux(is_load, ExceptionCause.LOAD_ACCESS_FAULT, ExceptionCause.STORE_ACCESS_FAULT)
                            self.report(m, rob_id=self.current_instr.rob_id, cause=cause)

                        m.d.sync += self.op_exception.eq(fetched.err)
                        m.d.sync += self.result_ready.eq(1)
                    with m.Else():
                        m.next = "Start"

                # result read ack or clear asserted
                with m.If(self.get_result_ack | (self.result_ready & ~self.current_instr.valid)):
                    m.d.sync += self.result_ready.eq(0)
                    m.d.sync += self.op_exception.eq(0)
                    m.next = "Start"

        return m


class LSUDummy(FuncBlock, Elaboratable):
    """
    Very simple LSU, which serializes all stores and loads.
    It isn't fully compliant with RiscV spec. Doesn't support checking if
    address is in correct range. Addresses have to be aligned.

    It uses the same interface as RS.

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
    precommit : Method
        Used to inform LSU that new instruction is ready to be retired.
    """

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
        self.precommit = Method(i=self.lsu_layouts.precommit)
        self.clear = Method()

        self.bus = bus

    def elaborate(self, platform):
        m = TModule()
        reserved = Signal()  # means that current_instr is reserved
        current_instr = Record(self.lsu_layouts.rs_data_layout + [("valid", 1)])

        m.submodules.internal = internal = LSUDummyInternals(self.gen_params, self.bus, current_instr)

        result_ready = internal.result_ready | ((current_instr.exec_fn.op_type == OpType.FENCE) & current_instr.valid)

        @def_method(m, self.select, ~reserved)
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

        @def_method(m, self.get_result, result_ready)
        def _():
            m.d.comb += internal.get_result_ack.eq(1)

            m.d.sync += current_instr.eq(0)
            m.d.sync += reserved.eq(0)

            return {
                "rob_id": current_instr.rob_id,
                "rp_dst": current_instr.rp_dst,
                "result": internal.loadedData,
                "exception": internal.op_exception,
            }

        @def_method(m, self.precommit)
        def _(rob_id: Value):
            with m.If(
                current_instr.valid & (rob_id == current_instr.rob_id) & (current_instr.exec_fn.op_type != OpType.FENCE)
            ):
                m.d.comb += internal.execute.eq(1)

        self.clear.add_conflict(self.select, priority=Priority.LEFT)
        self.clear.add_conflict(self.insert, priority=Priority.LEFT)
        self.clear.add_conflict(self.update, priority=Priority.LEFT)
        self.clear.add_conflict(self.get_result, priority=Priority.LEFT)

        @def_method(m, self.clear)
        def _():
            m.d.sync += current_instr.valid.eq(0)
            m.d.sync += reserved.eq(0)
            m.d.comb += internal.execute.eq(0)

        return m


class LSUBlockComponent(BlockComponentParams):
    def get_module(self, gen_params: GenParams) -> FuncBlock:
        connections = gen_params.get(DependencyManager)
        wb_master = connections.get_dependency(WishboneDataKey())
        unit = LSUDummy(gen_params, wb_master)
        connections.add_dependency(InstructionPrecommitKey(), unit.precommit)
        return unit

    def get_optypes(self) -> set[OpType]:
        return {OpType.LOAD, OpType.STORE, OpType.FENCE}

    def get_rs_entry_count(self) -> int:
        return 1
