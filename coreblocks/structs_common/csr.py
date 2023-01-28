from amaranth import *

from coreblocks.transactions import Method, def_method
from coreblocks.utils import assign
from coreblocks.params.genparams import GenParams
from coreblocks.params.layouts import RSLayouts, FuncUnitLayouts
from coreblocks.params.isa import Funct3


# +FENCE, see decode imm
# support like lsu
# make sure that rob is empty/all instuctions done?
# Register read/write handlers with methods
# TODO: Implement read only map (priv 2.1)
class CSRUnit(Elaboratable):
    def __init__(self, gen_params: GenParams, rob_single_instr: Signal, fetch_continue: Method):
        self.gen_params = gen_params

        self.rob_empty = rob_single_instr
        self.fetch_continue = fetch_continue

        # Standard RS interface
        self.rs_layouts = gen_params.get(RSLayouts)
        self.fu_layouts = gen_params.get(FuncUnitLayouts)
        self.select = Method(o=self.rs_layouts.select_out)
        self.insert = Method(i=self.rs_layouts.insert_in)
        self.update = Method(i=self.rs_layouts.update_in)
        self.accept = Method(o=self.fu_layouts.accept)

        # FIXME: Temporary size
        self.regfile = Array(Signal(gen_params.isa.xlen) for _ in range(64))

    def elaborate(self, platform):
        m = Module()

        reserved = Signal()
        ready_to_process = Signal()

        result_ready = Signal()
        current_result = Signal(self.gen_params.isa.xlen)

        instr = Record(self.rs_layouts.data_layout + [("valid", 1), ("orig_rp_s1", self.gen_params.phys_regs_bits)])

        m.d.comb += ready_to_process.eq(self.rob_empty & instr.valid & (instr.rp_s1 == 0))

        # RISCV Zicsr spec Table 1.1
        should_read_csr = Signal()
        m.d.comb += should_read_csr.eq(
            ((instr.exec_fn.funct3 == Funct3.CSRRW) & (instr.rp_dst != 0))
            | (instr.exec_fn.funct3 == Funct3.CSRRS)
            | (instr.exec_fn.funct3 == Funct3.CSRRC)
            | ((instr.exec_fn.funct3 == Funct3.CSRRWI) & (instr.rp_dst != 0))
            | (instr.exec_fn.funct3 == Funct3.CSRRSI)
            | (instr.exec_fn.funct3 == Funct3.CSRRCI)
        )

        should_write_csr = Signal()
        m.d.comb += should_write_csr.eq(
            (instr.exec_fn.funct3 == Funct3.CSRRW)
            | ((instr.exec_fn.funct3 == Funct3.CSRRS) & (instr.orig_rp_s1 != 0))
            | ((instr.exec_fn.funct3 == Funct3.CSRRC) & (instr.orig_rp_s1 != 0))
            | (instr.exec_fn.funct3 == Funct3.CSRRWI)
            | (instr.exec_fn.funct3 == Funct3.CSRRSI & (instr.s1_val != 0))
            | (instr.exec_fn.funct3 == Funct3.CSRRCI & (instr.s1_val != 0))
        )

        with m.FSM("Start"):  # TODO: eliminate FSM, it is not needed
            with m.State("Start"):
                with m.If(ready_to_process):
                    with m.If(should_read_csr):
                        m.next = "Read"
                    with m.Elif(should_write_csr):
                        m.next = "Write"
            with m.State("Read"):
                # TODO: Call registered side effects handlers
                m.d.sync += current_result.eq(self.regfile[instr.csr])
                with m.If(should_write_csr):
                    m.next = "Write"
                with m.Else():
                    m.next = "End"
            with m.State("Write"):
                # "may be modified as side effects of instruction execution. In these cases, if a CSR access
                # instruction reads a CSR, it reads the value prior to the execution of the instruction.
                # If a CSR access instruction writes such a CSR, the write is done instead of the increment. "
                with m.If((instr.exec_fn.funct3 == Funct3.CSRRW) | (instr.exec_fn.funct3 == Funct3.CSRRWI)):
                    m.d.sync += self.regfile[instr.csr].eq(instr.s1_val)
                with m.If((instr.exec_fn.funct3 == Funct3.CSRRS) | (instr.exec_fn.funct3 == Funct3.CSRRSI)):
                    m.d.sync += self.regfile[instr.csr].eq(current_result | instr.s1_val)  # always reads to instr
                with m.If((instr.exec_fn.funct3 == Funct3.CSRRC) | (instr.exec_fn.funct3 == Funct3.CSRRCI)):
                    m.d.sync += self.regfile[instr.csr].eq(current_result & (~instr.s1_val))  # always reads to instr
                m.next = "End"
            with m.State("End"):
                m.d.comb += result_ready.eq(1)
                m.next = "Start"

        @def_method(m, self.select, ~reserved)
        def _(arg):
            m.d.sync += reserved.eq(1)
            return 0  # only one CSR instruction is allowed

        @def_method(m, self.insert)
        def _(arg):
            # TODO: CSRR*I handling
            m.d.sync += assign(instr, arg.rs_data)
            # Information on rp_s1 is lost in update but we need it,
            # to decide if write side effects should be produced
            m.d.sync += instr.orig_rp_s1.eq(arg.rs_data.rp_s1)
            m.d.sync += instr.valid.eq(1)

        @def_method(m, self.update)
        def _(arg):
            with m.If(arg.tag == instr.rp_s1):
                m.d.sync += instr.s1_val.eq(arg.value)
                m.d.sync += instr.rp_s1.eq(0)

        @def_method(m, self.accept, result_ready)
        def _(arg):
            m.d.sync += reserved.eq(0)
            m.d.sync += instr.valid.eq(0)
            self.fetch_continue(m)
            return {
                "rob_id": instr.rob_id,
                "rp_dst": instr.rp_dst,
                "result": current_result,
            }

        return m
