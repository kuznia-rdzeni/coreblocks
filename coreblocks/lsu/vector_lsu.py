from amaranth import *
from amaranth.lib.coding import Decoder

from coreblocks.transactions import Method, def_method, Transaction, TModule
from coreblocks.transactions.lib import *
from coreblocks.params import *
from coreblocks.peripherals.wishbone import WishboneMaster
from coreblocks.utils import assign, ModuleLike, AssignType
from coreblocks.utils.protocols import FuncBlock
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.fu.vector_unit.utils import *

__all__ = ["VectorLSU"]

class VectorLSUDummyInternals(Elaboratable):
    def __init__(self, gen_params: GenParams, bus: WishboneMaster, current_instr: Record, write_vrf : list[Method], read_req_vrf : list[Method], read_resp_vrf : list[Method]) -> None:
        self.gen_params = gen_params
        self.v_params = self.gen_params.v_params
        self.current_instr = current_instr
        self.bus = bus
        self.write_vrf = write_vrf
        self.read_req_vrf = read_req_vrf
        self.read_resp_vrf = read_resp_vrf

        self.dependency_manager = self.gen_params.get(DependencyManager)
        self.report = self.dependency_manager.get_dependency(ExceptionReportKey())

        self.get_result_ack = Signal()
        self.result_ready = Signal()
        self.execute = Signal()
        self.op_exception = Signal()

        self.elems_counter = Signal(bits_for(self.gen_params.v_params.bytes_in_vlen))
        self.elen_counter =  Signal(bits_for(self.gen_params.v_params.elens_in_vlen))
        self.bank_id = Signal(log2_int(self.v_params.register_bank_count, False))
        self.local_addr = Signal(log2_int(self.gen_params.v_params.elens_in_bank, False))

    def calculate_addr(self, m: ModuleLike):
        addr = Signal(self.gen_params.isa.xlen)
        m.d.comb += addr.eq(self.current_instr.s1_val + (self.elen_counter << 2))
        return addr

    def prepare_bytes_mask(self, m: TModule, addr: Signal) -> Signal:
        mask = Signal(self.v_params.bytes_in_elen)
        elem_mask = Signal(self.v_params.bytes_in_elen)
        m.submodules.binary_to_onehot = binary_to_onehot = Decoder(self.v_params.bytes_in_elen + 1)
        diff = Signal.like(self.current_instr.vtype.vl)
        m.d.top_comb += diff.eq(self.current_instr.vtype.vl - self.elems_counter)
        m.d.top_comb += binary_to_onehot.i.eq(diff)
        last =Signal()
        with m.Switch(self.current_instr.vtype.sew):
            for sew_iter in SEW:
                with m.Case(sew_iter):
                    m.d.av_comb += last.eq(diff < self.v_params.elen // eew_to_bits(sew_iter))
        m.d.av_comb += elem_mask.eq(
                Mux(
                    last,
                    binary_to_onehot.o - 1,
                    2 ** (self.v_params.elen // eew_to_bits(EEW.w8)) - 1,
                    )
                )
        m.d.top_comb += mask.eq(elem_mask_to_byte_mask(m, self.v_params, elem_mask, self.current_instr.vtype.sew))
        return mask

    def check_align(self, m: TModule, addr: Signal):
        aligned = Signal()
        #TODO Allow for aligments to elements instead of aligment to ELEN
        match self.v_params.elen:
            case 64:
                m.d.comb += aligned.eq(addr[0:3] == 0)
            case 32:
                m.d.comb += aligned.eq(addr[0:2] == 0)
            case 16:
                m.d.comb += aligned.eq(addr[0] == 0)
            case 8:
                m.d.comb += aligned.eq(1)
        return aligned

    def counters_increase(self, m:TModule):
        with m.Switch(self.current_instr.vtype.sew):
            for sew_iter in SEW:
                with m.Case(sew_iter):
                    m.d.sync += self.elems_counter.eq(self.elems_counter + self.v_params.elen // eew_to_bits(sew_iter))
        m.d.sync += self.elen_counter.eq(self.elen_counter + 1)
        with m.If(self.local_addr + 1 == self.v_params.elens_in_bank):
            m.d.sync += self.local_addr.eq(0)
            m.d.sync += self.bank_id.eq(self.bank_id + 1)
        with m.Else():
            m.d.sync += self.local_addr.eq(self.local_addr + 1)

    def handle_load(self, m : TModule, request : Value, bytes_mask, addr, restart : Value):
        cast_dst_vrp_id = Signal(range(self.v_params.vrp_count))
        m.d.top_comb += cast_dst_vrp_id.eq(self.current_instr.rp_dst.id)
        with m.FSM():
            with m.State("ReqFromMem"):
                with m.If(restart):
                    m.d.sync += self.local_addr.eq(0)
                    m.d.sync += self.bank_id.eq(0)
                    m.d.sync += self.elems_counter.eq(0)
                    m.d.sync += self.elen_counter.eq(0)
                with m.If((self.elems_counter >= self.current_instr.vtype.vl) & request & ~self.result_ready):
                    m.d.sync += self.op_exception.eq(0)
                    m.d.sync += self.result_ready.eq(1)
                with m.Else():
                    with Transaction(name = "load_req_from_mem_trans").body(m, request = request & ~self.result_ready):
                        self.bus.request(m, addr=addr >> 2, we=0, sel=0, data=0)
                        m.next = "RespFromMem"
            with m.State("RespFromMem"):
                with Transaction(name= "load_resp_from_mem_trans").body(m, request = request):
                    fetched = self.bus.result(m)
                    with m.If(fetched.err):
                        cause = ExceptionCause.LOAD_ACCESS_FAULT
                        self.report(m, rob_id=self.current_instr.rob_id, cause=cause)
                        m.d.sync += self.op_exception.eq(fetched.err)
                        m.d.sync += self.result_ready.eq(1)
                    with m.Else():
                        with m.Switch(self.bank_id):
                            for i in range(self.v_params.register_bank_count):
                                with m.Case(i):
                                    self.write_vrf[i](m, addr = self.local_addr, vrp_id = cast_dst_vrp_id, valid_mask = bytes_mask, data = fetched.data)
                        self.counters_increase(m)
                    m.next = "ReqFromMem"

    def handle_store(self, m : TModule, request : Value, bytes_mask, addr, restart : Value):
        cast_s3_vrp_id = Signal(range(self.v_params.vrp_count))
        m.d.top_comb += cast_s3_vrp_id.eq(self.current_instr.rp_s3.id)
        with m.FSM():
            with m.State("ReqFromReg"):
                with m.If(restart):
                    m.d.sync += self.local_addr.eq(0)
                    m.d.sync += self.bank_id.eq(0)
                    m.d.sync += self.elems_counter.eq(0)
                    m.d.sync += self.elen_counter.eq(0)
                with m.If((self.elems_counter >= self.current_instr.vtype.vl) & request & ~self.result_ready):
                    m.d.sync += self.op_exception.eq(0)
                    m.d.sync += self.result_ready.eq(1)
                with m.Else():
                    with Transaction(name= "store_req_reg_trans").body(m, request = request & ~self.result_ready):
                        for i in condition_switch(m,self.bank_id, self.v_params.register_bank_count):
                            self.read_req_vrf[i](m, addr = self.local_addr, vrp_id = cast_s3_vrp_id)
                        m.next = "RespFromReg"
            with m.State("RespFromReg"):
                with Transaction(name = "store_resp_reg_trans").body(m, request = request):
                    resp = Record(self.read_resp_vrf[0].data_out.layout)
                    for i in condition_switch(m,self.bank_id, self.v_params.register_bank_count):
                        m.d.comb += assign(resp, self.read_resp_vrf[i](m), fields = AssignType.ALL)
                    self.bus.request(m, addr=addr >> 2, we=1, sel=bytes_mask, data=resp.data)
                    m.next = "RespFromMem"
            with m.State("RespFromMem"):
                with Transaction(name = "store_resp_from_mem_trans").body(m, request = request):
                    fetched = self.bus.result(m)
                    with m.If(fetched.err):
                        cause = ExceptionCause.STORE_ACCESS_FAULT
                        self.report(m, rob_id=self.current_instr.rob_id, cause=cause)
                        m.d.sync += self.op_exception.eq(fetched.err)
                        m.d.sync += self.result_ready.eq(1)
                    with m.Else():
                        self.counters_increase(m)
                    m.next = "ReqFromReg"


    def elaborate(self, platform):
        m = TModule()

        instr_ready = (
            (self.current_instr.rp_s2_rdy == 1)
            & (self.current_instr.rp_s3_rdy == 1)
            & (self.current_instr.rp_v0_rdy == 1)
            & self.current_instr.valid
            & ~self.result_ready
        )

        is_load = self.current_instr.exec_fn.op_type == OpType.V_LOAD

        addr = self.calculate_addr(m)
        aligned = self.check_align(m, addr)
        bytes_mask = self.prepare_bytes_mask(m, addr)

        self.handle_load(m,  instr_ready & is_load & aligned, bytes_mask, addr, self.get_result_ack)
        self.handle_store(m,  instr_ready & self.execute & aligned & ~is_load, bytes_mask, addr, self.get_result_ack)
        with Transaction(name= "miss_align_trans").body(m, request = instr_ready & (is_load | self.execute) & ~aligned):
            m.d.sync += self.op_exception.eq(1)
            m.d.sync += self.result_ready.eq(1)

            cause = Mux(
                is_load, ExceptionCause.LOAD_ADDRESS_MISALIGNED, ExceptionCause.STORE_ADDRESS_MISALIGNED
            )
            self.report(m, rob_id=self.current_instr.rob_id, cause=cause)

        with m.If(self.get_result_ack):
            m.d.sync += self.result_ready.eq(0)
            m.d.sync += self.op_exception.eq(0)


        return m


class VectorLSU(FuncBlock, Elaboratable):
    def __init__(self, gen_params: GenParams, bus: WishboneMaster, write_vrf : list[Method], read_req_vrf : list[Method], read_resp_vrf : list[Method]) -> None:
        self.gen_params = gen_params
        self.fu_layouts = gen_params.get(FuncUnitLayouts)
        self.v_lsu_layouts = gen_params.get(VectorLSULayouts)

        self.select = Method(o=self.v_lsu_layouts.rs_select_out)
        self.insert = Method(i=self.v_lsu_layouts.rs_insert_in)
        self.update = Method(i=self.v_lsu_layouts.rs_update_in)
        self.get_result = Method(o=self.fu_layouts.accept)
        self.precommit = Method(i=self.v_lsu_layouts.precommit)

        self.bus = bus
        self.write_vrf = write_vrf
        self.read_req_vrf = read_req_vrf
        self.read_resp_vrf = read_resp_vrf
        
        if self.gen_params.isa.xlen != self.gen_params.v_params.elen or self.gen_params.v_params.elen != 32:
            raise ValueError("Vector LSU don't support XLEN != ELEN != 32 yet.")

    def elaborate(self, platform):
        m = TModule()
        reserved = Signal()  # means that current_instr is reserved
        current_instr = Record(self.v_lsu_layouts.rs_data_layout + [("valid", 1)])

        m.submodules.internal = internal = VectorLSUDummyInternals(self.gen_params, self.bus, current_instr, self.write_vrf, self.read_req_vrf, self.read_resp_vrf)

        result_ready = internal.result_ready 

        @def_method(m, self.select, ~reserved)
        def _():
            # We always return 0, because we have only one place in instruction storage.
            m.d.sync += reserved.eq(1)
            return {"rs_entry_id": 0}

        @def_method(m, self.insert, reserved & ~current_instr.valid)
        def _(rs_data: Record, rs_entry_id: Value):
            m.d.sync += assign(current_instr, rs_data)
            m.d.sync += current_instr.valid.eq(1)
            # no support for instructions which use v0 or vs2, so don't wait for them
            m.d.sync += current_instr.rp_v0_rdy.eq(1)
            m.d.sync += current_instr.rp_s2_rdy.eq(1)

        @def_method(m, self.update)
        def _(tag: Value, value: Value):
            with m.If(current_instr.rp_s2 == tag):
                m.d.sync += current_instr.rp_s2_rdy.eq(1)
            with m.If(current_instr.rp_s3 == tag):
                m.d.sync += current_instr.rp_s3_rdy.eq(1)
            with m.If(current_instr.rp_v0 == tag):
                m.d.sync += current_instr.rp_v0_rdy.eq(1)

        @def_method(m, self.get_result, result_ready)
        def _():
            m.d.comb += internal.get_result_ack.eq(1)

            m.d.sync += current_instr.eq(0)
            m.d.sync += reserved.eq(0)

            return {
                "rob_id": current_instr.rob_id,
                "rp_dst": current_instr.rp_dst,
                "result": 0,
                "exception": internal.op_exception,
            }

        @def_method(m, self.precommit)
        def _(rob_id: Value):
            with m.If( current_instr.valid & (rob_id == current_instr.rob_id) ):
                m.d.comb += internal.execute.eq(1)

        return m
