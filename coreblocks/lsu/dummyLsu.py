from amaranth import *

from transactron import Method, def_method, Transaction, TModule
from coreblocks.params import *
from coreblocks.peripherals.wishbone import WishboneMaster
from transactron.lib.connectors import Forwarder
from transactron.utils import assign, ModuleLike
from coreblocks.utils.protocols import FuncBlock


__all__ = ["LSUDummy", "LSUBlockComponent"]


class LSURequesterWB(Elaboratable):
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
        self.bus = bus

#        self.loadedData = Signal(self.gen_params.isa.xlen)
#        self.get_result_ack = Signal()
#        self.result_ready = Signal()
#        self.execute = Signal()
#        self.op_exception = Signal()
        
        lsu_layouts = gen_params.get(LSULayouts)

        self.issue = Method(i=lsu_layouts.issue, o=lsu_layouts.issue_out)
        self.accept = Method(o=lsu_layouts.accept)

    def prepare_bytes_mask(self, m: ModuleLike, funct3: Value, addr: Value) -> Signal:
        mask_len = self.gen_params.isa.xlen // self.bus.wb_params.granularity
        mask = Signal(mask_len)
        with m.Switch(funct3):
            with m.Case(Funct3.B, Funct3.BU):
                m.d.comb += mask.eq(0x1 << addr[0:2])
            with m.Case(Funct3.H, Funct3.HU):
                m.d.comb += mask.eq(0x3 << (addr[1] << 1))
            with m.Case(Funct3.W):
                m.d.comb += mask.eq(0xF)
        return mask

    def postprocess_load_data(self, m: ModuleLike, funct3: Value, raw_data: Value, addr: Value):
        data = Signal.like(raw_data)
        with m.Switch(funct3):
            with m.Case(Funct3.B, Funct3.BU):
                tmp = Signal(8)
                m.d.comb += tmp.eq((raw_data >> (addr[0:2] << 3)) & 0xFF)
                with m.If(funct3 == Funct3.B):
                    m.d.comb += data.eq(tmp.as_signed())
                with m.Else():
                    m.d.comb += data.eq(tmp)
            with m.Case(Funct3.H, Funct3.HU):
                tmp = Signal(16)
                m.d.comb += tmp.eq((raw_data >> (addr[1] << 4)) & 0xFFFF)
                with m.If(funct3 == Funct3.H):
                    m.d.comb += data.eq(tmp.as_signed())
                with m.Else():
                    m.d.comb += data.eq(tmp)
            with m.Case():
                m.d.comb += data.eq(raw_data)
        return data

    def prepare_data_to_save(self, m: ModuleLike, funct3: Value, raw_data: Value, addr: Value):
        data = Signal.like(raw_data)
        with m.Switch(funct3):
            with m.Case(Funct3.B):
                m.d.comb += data.eq(raw_data[0:8] << (addr[0:2] << 3))
            with m.Case(Funct3.H):
                m.d.comb += data.eq(raw_data[0:16] << (addr[1] << 4))
            with m.Case():
                m.d.comb += data.eq(raw_data)
        return data

    def check_align(self, m: TModule, funct3: Value, addr: Value):
        aligned = Signal()
        with m.Switch(funct3):
            with m.Case(Funct3.W):
                m.d.comb += aligned.eq(addr[0:2] == 0)
            with m.Case(Funct3.H, Funct3.HU):
                m.d.comb += aligned.eq(addr[0] == 0)
            with m.Case():
                m.d.comb += aligned.eq(1)
        return aligned

    def elaborate(self, platform):
        m = TModule()

#        instr_ready = (
#            (self.current_instr.rp_s1 == 0)
#            & (self.current_instr.rp_s2 == 0)
#            & self.current_instr.valid
#            & ~self.result_ready
#        )

#        is_load = self.current_instr.exec_fn.op_type == OpType.LOAD

        addr_reg = Signal(self.gen_params.isa.xlen)
        funct3_reg = Signal(Funct3)
        store_reg = Signal()
        request_sent = Signal()

        @def_method(m, self.issue, ~request_sent)
        def _(addr: Value, data: Value, funct3: Value, store: Value):
            exception = Signal()
            cause = Signal(ExceptionCause)

            aligned = self.check_align(m, funct3, addr)
            bytes_mask = self.prepare_bytes_mask(m, funct3, addr)
            wb_data = self.prepare_data_to_save(m, funct3, data, addr)

            with m.If(aligned):
                self.bus.request(m, addr=addr >> 2, we=store, sel=bytes_mask, data=wb_data)
                m.d.sync += request_sent.eq(1)
                m.d.sync += addr_reg.eq(addr)
                m.d.sync += funct3_reg.eq(funct3)
                m.d.sync += store_reg.eq(store)
            with m.Else():
                m.d.av_comb += exception.eq(1)
                m.d.av_comb += cause.eq(Mux(
                                store, ExceptionCause.STORE_ADDRESS_MISALIGNED, ExceptionCause.LOAD_ADDRESS_MISALIGNED
                            ))

            return {"exception": exception, "cause": cause}

        @def_method(m, self.accept, request_sent)
        def _():
            exception = Signal()
            cause = Signal(ExceptionCause)

            fetched = self.bus.result(m)
            m.d.sync += request_sent.eq(0)

            data = self.postprocess_load_data(m, funct3_reg, fetched.data, addr_reg)
                    
            with m.If(fetched.err):
                m.d.av_comb += exception.eq(1)
                m.d.av_comb += cause.eq(Mux(store_reg, ExceptionCause.STORE_ACCESS_FAULT, ExceptionCause.LOAD_ACCESS_FAULT))
            
            return {"data": data, "exception": exception, "cause": cause}

#        with m.FSM("Start"):
#            with m.State("Start"):
#                with m.If(instr_ready & (self.execute | is_load)):
#                    with m.If(aligned):
#                        with Transaction().body(m):
#                            self.bus.request(m, addr=addr >> 2, we=~is_load, sel=bytes_mask, data=data)
#                            m.next = "End"
#                    with m.Else():
#                        with Transaction().body(m):
#                            m.d.sync += self.op_exception.eq(1)
#                            m.d.sync += self.result_ready.eq(1)
#
#                            cause = Mux(
#                                is_load, ExceptionCause.LOAD_ADDRESS_MISALIGNED, ExceptionCause.STORE_ADDRESS_MISALIGNED
#                            )
#                            self.report(m, rob_id=self.current_instr.rob_id, cause=cause)
#
#                            m.next = "End"

#            with m.State("End"):
#                with Transaction().body(m):
#                    fetched = self.bus.result(m)
#
#                    m.d.sync += self.loadedData.eq(self.postprocess_load_data(m, fetched.data, addr))
#
#                    with m.If(fetched.err):
#                        cause = Mux(is_load, ExceptionCause.LOAD_ACCESS_FAULT, ExceptionCause.STORE_ACCESS_FAULT)
#                        self.report(m, rob_id=self.current_instr.rob_id, cause=cause)
#
#                    m.d.sync += self.op_exception.eq(fetched.err)
#                    m.d.sync += self.result_ready.eq(1)
#
#                with m.If(self.get_result_ack):
#                    m.d.sync += self.result_ready.eq(0)
#                    m.d.sync += self.op_exception.eq(0)
#                    m.next = "Start"

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

        dependency_manager = self.gen_params.get(DependencyManager)
        self.report = dependency_manager.get_dependency(ExceptionReportKey())

        self.insert = Method(i=self.lsu_layouts.rs.insert_in)
        self.select = Method(o=self.lsu_layouts.rs.select_out)
        self.update = Method(i=self.lsu_layouts.rs.update_in)
        self.get_result = Method(o=self.fu_layouts.accept)
        self.precommit = Method(i=self.lsu_layouts.precommit)

        self.bus = bus

    def elaborate(self, platform):
        m = TModule()
        reserved = Signal()  # current_instr is reserved
        valid = Signal()  # current_instr is valid
        execute = Signal()  # start execution
        issued = Signal()  # instruction was issued to the bus
        current_instr = Record(self.lsu_layouts.rs.data_layout)

        m.submodules.requester = requester = LSURequesterWB(self.gen_params, self.bus)

        m.submodules.results = results = self.forwarder = Forwarder(self.lsu_layouts.accept)

        instr_ready = (
            (current_instr.rp_s1 == 0)
            & (current_instr.rp_s2 == 0)
            & valid
        )

        instr_is_fence = Signal()
        m.d.comb += instr_is_fence.eq(current_instr.exec_fn.op_type == OpType.FENCE)

        instr_is_load = Signal()
        m.d.comb += instr_is_load.eq(current_instr.exec_fn.op_type == OpType.LOAD)

        @def_method(m, self.select, ~reserved)
        def _():
            # We always return 0, because we have only one place in instruction storage.
            m.d.sync += reserved.eq(1)
            return {"rs_entry_id": 0}

        @def_method(m, self.insert)
        def _(rs_data: Record, rs_entry_id: Value):
            m.d.sync += assign(current_instr, rs_data)
            m.d.sync += valid.eq(1)

        @def_method(m, self.update)
        def _(reg_id: Value, reg_val: Value):
            with m.If(current_instr.rp_s1 == reg_id):
                m.d.sync += current_instr.s1_val.eq(reg_val)
                m.d.sync += current_instr.rp_s1.eq(0)
            with m.If(current_instr.rp_s2 == reg_id):
                m.d.sync += current_instr.s2_val.eq(reg_val)
                m.d.sync += current_instr.rp_s2.eq(0)

        with Transaction().body(m, request=instr_ready & ~issued & ~instr_is_fence & (execute | instr_is_load)):
            m.d.sync += issued.eq(1)
            res = requester.issue(m, addr=current_instr.s1_val + current_instr.imm, data=current_instr.s2_val, funct3=current_instr.exec_fn.funct3, store=~instr_is_load)
            with m.If(res["exception"]):
                results.write(m, data=0, exception=res["exception"], cause=res["cause"])

        with Transaction().body(m, request=instr_ready & ~issued & instr_is_fence):
            m.d.sync += issued.eq(1)
            results.write(m, data=0, exception=0, cause=0)

        with Transaction().body(m, request=instr_ready):
            res = requester.accept(m)
            results.write(m, res)

        @def_method(m, self.get_result)
        def _():
            res = results.read(m)

            with m.If(res["exception"]):
                self.report(m, rob_id=current_instr.rob_id, cause=res["cause"])

            m.d.sync += issued.eq(0)
            m.d.sync += valid.eq(0)
            m.d.sync += reserved.eq(0)

            return {
                "rob_id": current_instr.rob_id,
                "rp_dst": current_instr.rp_dst,
                "result": res["data"],
                "exception": res["exception"],
            }

        @def_method(m, self.precommit)
        def _(rob_id: Value):
            with m.If(
                valid & (rob_id == current_instr.rob_id) & ~instr_is_fence
            ):
                m.d.comb += execute.eq(1)

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
