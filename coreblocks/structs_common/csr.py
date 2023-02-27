from amaranth import *

from coreblocks.transactions import Method, def_method, Transaction
from coreblocks.utils import assign
from coreblocks.params.genparams import GenParams
from coreblocks.params.layouts import FuncUnitLayouts, CSRLayouts
from coreblocks.params.isa import Funct3


# +FENCE, see decode imm
# make sure that rob is empty/all instuctions done?
# TODO: Implement read only map (priv 2.1)


class CSRRegister(Elaboratable):
    def __init__(self, csr_number: int, gen_params: GenParams, *, ro_bits: int = 0):
        self.gen_params = gen_params
        self.csr_number = csr_number
        self.ro_bits = ro_bits

        csr_layouts = gen_params.get(CSRLayouts)

        self.read = Method(o=csr_layouts.read)
        self.write = Method(i=csr_layouts.write)

        # Methods connected automatically by CSRUnit
        self._fu_read = Method(o=csr_layouts._fu_read)
        self._fu_write = Method(i=csr_layouts._fu_write)

        self.value = Signal(gen_params.isa.xlen)
        self.side_effects = Record({("read", 1), ("write", 1)})

    def elaborate(self, platform):
        m = Module()

        internal_method_layout = {("data", self.gen_params.isa.xlen), ("active", 1)}
        write_internal = Record(internal_method_layout)
        fu_write_internal = Record(internal_method_layout)

        m.d.sync += self.side_effects.eq(0)

        @def_method(m, self.write)
        def _(arg):
            m.d.comb += write_internal.data.eq(arg.data)
            m.d.comb += write_internal.active.eq(1)

        @def_method(m, self._fu_write)
        def _(arg):
            m.d.comb += fu_write_internal.data.eq(arg.data)
            m.d.comb += fu_write_internal.active.eq(1)
            m.d.sync += self.side_effects.write.eq(1)

        @def_method(m, self.read)
        def _(arg):
            return {"data": self.value, "read": self.side_effects.read, "written": self.side_effects.write}

        @def_method(m, self._fu_read)
        def _(arg):
            m.d.sync += self.side_effects.read.eq(1)
            return self.value

        # Writes from instructions have priority
        with m.If(fu_write_internal.active & write_internal.active):
            m.d.sync += self.value.eq((fu_write_internal.data & ~self.ro_bits) | (write_internal.data & self.ro_bits))
        with m.Elif(fu_write_internal.active):
            m.d.sync += self.value.eq((fu_write_internal.data & ~self.ro_bits) | (self.value & self.ro_bits))
        with m.Elif(write_internal.active):
            m.d.sync += self.value.eq(write_internal.data)

        return m


class CSRUnit(Elaboratable):
    def __init__(self, gen_params: GenParams, rob_single_instr: Signal, fetch_continue: Method):
        self.gen_params = gen_params

        self.rob_empty = rob_single_instr
        self.fetch_continue = fetch_continue

        # Standard RS interface
        self.csr_layouts = gen_params.get(CSRLayouts)
        self.fu_layouts = gen_params.get(FuncUnitLayouts)
        self.select = Method(o=self.csr_layouts.rs_select_out)
        self.insert = Method(i=self.csr_layouts.rs_insert_in)
        self.update = Method(i=self.csr_layouts.rs_update_in)
        self.accept = Method(o=self.fu_layouts.accept)

        self.regfile: dict[int, tuple[Method, Method]] = {}

    def register(self, csr: CSRRegister):
        if csr.csr_number in self.regfile:
            raise RuntimeError(f"CSR number {csr.csr_number} already registered")
        self.regfile[csr.csr_number] = (csr._fu_read, csr._fu_write)

    def elaborate(self, platform):
        m = Module()

        reserved = Signal()
        ready_to_process = Signal()
        done = Signal()

        current_result = Signal(self.gen_params.isa.xlen)

        instr = Record(self.csr_layouts.rs_data_layout + [("valid", 1), ("orig_rp_s1", self.gen_params.phys_regs_bits)])

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

        # Methods used within this Tranaction are CSRRegister internal _fu_(read|write) handlers which are always ready
        with Transaction().body(m, request=(ready_to_process & ~done)):
            with m.Switch(instr.csr):
                for csr_number, methods in self.regfile.items():
                    read, write = methods
                    with m.Case(csr_number):
                        read_val = Signal(self.gen_params.isa.xlen)
                        with m.If(should_read_csr & ~done):
                            m.d.comb += read_val.eq(read(m))
                            m.d.sync += current_result.eq(read_val)

                        with m.If(should_write_csr & ~done):
                            write_val = Signal(self.gen_params.isa.xlen)
                            with m.If((instr.exec_fn.funct3 == Funct3.CSRRW) | (instr.exec_fn.funct3 == Funct3.CSRRWI)):
                                m.d.comb += write_val.eq(instr.s1_val)
                            with m.If((instr.exec_fn.funct3 == Funct3.CSRRS) | (instr.exec_fn.funct3 == Funct3.CSRRSI)):
                                m.d.comb += write_val.eq(read_val | instr.s1_val)
                            with m.If((instr.exec_fn.funct3 == Funct3.CSRRC) | (instr.exec_fn.funct3 == Funct3.CSRRCI)):
                                m.d.comb += write_val.eq(read_val & (~instr.s1_val))

                            write(m, write_val)
                with m.Default():
                    pass  # TODO : invalid csr number handling

            m.d.sync += done.eq(1)

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

        @def_method(m, self.accept, done)
        def _(arg):
            m.d.sync += reserved.eq(0)
            m.d.sync += instr.valid.eq(0)
            m.d.sync += done.eq(0)
            self.fetch_continue(m)
            return {
                "rob_id": instr.rob_id,
                "rp_dst": instr.rp_dst,
                "result": current_result,
            }

        return m
