from amaranth import *
from amaranth.lib.coding import Decoder

from coreblocks.transactions import Method, def_method, Transaction, TModule
from coreblocks.params import *
from coreblocks.peripherals.wishbone import WishboneMaster
from coreblocks.utils import assign, ModuleLike
from coreblocks.utils.protocols import FuncBlock
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.fu.vector_unit.utils import *



class VectorLSUDummyInternals(Elaboratable):
    def __init__(self, gen_params: GenParams, bus: WishboneMaster, current_instr: Record, write_vrf : list[Method], read_req_vrf : Method, read_resp_vrf : Method) -> None:
        self.gen_params = gen_params
        self.v_params = self.gen_params.v_params
        self.current_instr = current_instr
        self.bus = bus
        self.write_vrf = write_vrf
        self.read_req_vrf = read_req_vrf
        self.read_resp_vrf = read_resp_vrf

        self.dependency_manager = self.gen_params.get(DependencyManager)
        self.report = self.dependency_manager.get_dependency(ExceptionReportKey())

        self.loadedData = Signal(self.gen_params.v_params.elen)
        self.get_result_ack = Signal()
        self.result_ready = Signal()
        self.execute = Signal()
        self.op_exception = Signal()

        self.elems_counter = Signal(bits_for(self.gen_params.v_params.bytes_in_vlen))
        self.elen_counter =  Signal(bits_for(self.gen_params.v_params.elens_in_vlen))
        self.bank_id = Signal(log2_int(self.v_params.register_bank_count, False))
        self.local_addr = Signal(bits_for(self.gen_params.v_params.elens_in_bank))

    def calculate_addr(self, m: ModuleLike):
        addr = Signal(self.gen_params.isa.xlen)
        m.d.comb += addr.eq(self.current_instr.s1_val + self.elen_counter)
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
        m.d.top_comb += elem_mask_to_byte_mask(m, self.v_params, elem_mask, self.current_instr.vtype.eew)
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

    def handle_load(self, m : TModule, request : Value, bytes_mask, addr, restart : Value):
        with m.FSM():
            with m.State("ReqFromMem"):
                with m.If(restart):
                    m.d.sync += [
                            self.local_addr.eq(0),
                            self.bank_id.eq(0),
                            self.elems_counter.eq(0),
                            self.elen_counter.eq(0)
                            ]
                with m.If(self.elems_counter >= self.current_instr.vtype.vl):
                    m.d.sync += self.op_exception.eq(0)
                    m.d.sync += self.result_ready.eq(1)
                with m.Else():
                    with Transaction().body(m, request = request & ~self.result_ready):
                        self.bus.request(m, addr=addr >> 2, we=0, sel=bytes_mask, data=0)
                        m.next = "RespFromMem"
            with m.State("RespFromMem"):
                with Transaction().body(m, request = request):
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
                                    self.write_vrf[i](m, addr = self.local_addr, vrp_id = self.current_instr.rp_dst.id, valid_mask = bytes_mask, value = fetched.data)
                        with m.Switch(self.current_instr.vtype.sew):
                            for sew_iter in SEW:
                                with m.Case(sew_iter):
                                    m.d.sync += self.elems_counter.eq(self.elems_counter + self.v_params.eew_to_elems_in_bank[sew_iter])
                        m.d.sync += self.elen_counter.eq(self.elen_counter + 1)
                        with m.If(self.local_addr + 1 == self.v_params.elens_in_bank):
                            m.d.sync += self.local_addr.eq(0)
                            m.d.sync += self.bank_id.eq(self.bank_id + 1)
                        with m.Else():
                            m.d.sync += self.local_addr.eq(self.local_addr + 1)
                    m.next = "ReqFromMem"



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

        with m.FSM("Start"):
            with m.State("Start"):
                request_cond = Signal()
                m.d.top_comb += request_cond.eq(instr_ready & (self.execute | is_load))
                with Transaction().body(m, request = request_cond & aligned):
                    self.bus.request(m, addr=addr >> 2, we=~is_load, sel=bytes_mask, data=data)
                    m.next = "End"

                with Transaction().body(m, request = request_cond & ~aligned):
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

                    with m.If(fetched.err):
                        cause = Mux(is_load, ExceptionCause.LOAD_ACCESS_FAULT, ExceptionCause.STORE_ACCESS_FAULT)
                        self.report(m, rob_id=self.current_instr.rob_id, cause=cause)

                    m.d.sync += self.op_exception.eq(fetched.err)
                    m.d.sync += self.result_ready.eq(1)

                with m.If(self.get_result_ack):
                    m.d.sync += self.result_ready.eq(0)
                    m.d.sync += self.op_exception.eq(0)
                    m.next = "Start"

        return m

class HandleLoad(Elaboratable):
    def __init__(self,  gen_params: GenParams, bus: WishboneMaster, write_vrf : Method ):
        self.gen_params = gen_params
        self.bus = bus
        self.write_vrf = write_vrf

    def elaborate(self, platform):
        m = TModule()

        self.current_instr = current_instr


        return m


class VectorLSU(FuncBlock, Elaboratable):
    def __init__(self, gen_params: GenParams, bus: WishboneMaster, write_vrf : Method, read_req_vrf : Method, read_resp_vrf : Method) -> None:
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
        
        if self.gen_params.isa.xlen != self.gen_params.v_params.elen:
            raise ValueError("Vector LSU don't support XLEN != ELEN yet.")

    def elaborate(self, platform):
        m = TModule()
        reserved = Signal()  # means that current_instr is reserved
        current_instr = Record(self.v_lsu_layouts.rs_data_layout + [("valid", 1)])

        m.submodules.internal = internal = VectorLSUDummyInternals(self.gen_params, self.bus, current_instr)

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
                "result": internal.loadedData,
                "exception": internal.op_exception,
            }

        @def_method(m, self.precommit)
        def _(rob_id: Value):
            with m.If(
                current_instr.valid & (rob_id == current_instr.rob_id) & (current_instr.exec_fn.op_type != OpType.FENCE)
            ):
                m.d.comb += internal.execute.eq(1)

        return m
