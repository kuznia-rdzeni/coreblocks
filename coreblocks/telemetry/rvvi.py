from amaranth import *
from amaranth.lib import memory
from amaranth.lib.data import ArrayLayout, View
from amaranth.lib.wiring import Component, Out

from transactron import *
from transactron.utils import DependencyContext, make_layout
from transactron.utils.amaranth_ext.component_interface import ComponentInterface, COut

from coreblocks.arch.isa_consts import PrivilegeLevel, XlenEncoding
from coreblocks.interface.keys import CSRInstancesKey
from coreblocks.params import GenParams
from coreblocks.interface.layouts import RVVILayouts


__all__ = [
    "RVVIRetireInterface",
    "RVVIHartCollector",
    "RVVIAggregator",
]


class RVVIRetireInterface(ComponentInterface):
    def __init__(self, ilen: int, xlen: int, flen: int = 0, vlen: int = 0):
        self.valid = COut(1)
        self.order = COut(64)

        self.insn = COut(ilen)
        self.trap = COut(1)
        self.debug_mode = COut(1)
        self.intr = COut(1)  # optional
        self.halt = COut(1)  # optional

        self.pc_rdata = COut(xlen)
        self.pc_wdata = COut(xlen)  # optional

        self.x_wdata = COut(ArrayLayout(xlen, 32))
        self.x_wb = COut(32)
        self.f_wdata = COut(ArrayLayout(flen, 32))
        self.f_wb = COut(32)
        self.v_wdata = COut(ArrayLayout(vlen, 32))
        self.v_wb = COut(32)

        # FIXME: there are 4096 CSRs in the interface, that makes ~130k wide wire,
        # but amaranth only supports up to 2**16 wide wires
        self.csr = COut(ArrayLayout(xlen, 0))
        self.csr_wb = COut(0)

        self.lrsc_cancel = COut(1)

        self.mode = COut(2)  # optional
        self.mode_virt = COut(1)  # optional
        self.ixl = COut(2)  # optional


class RVVIHartCollector(Component):
    """A module that collects information required for RVVI-TRACE interface for a single hart.

    Currently doesn't implement `pc_wdata`, `f_*`, `v_*`, `csr_*`.

    Made as a simulation module, so critical path nor area is not optimized.
    Either way exposing more than 128k wires is not feasible.
    """

    retire_port: View
    """Single hart worth of data of RVVI-TRACE interface."""

    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params
        self.layouts = gen_params.get(RVVILayouts)

        self.frontend_ports = gen_params.frontend_superscalarity
        self.reg_write_ports = gen_params.announcement_superscalarity
        self.retire_ports = gen_params.retirement_superscalarity

        self.register_ftq = Method(i=self.layouts.register_ftq)
        self.register_ftq_rob_assoc = Methods(self.frontend_ports, i=self.layouts.register_ftq_rob_assoc)
        self.register_reg_write = Methods(self.reg_write_ports, i=self.layouts.register_reg_write)
        self.finalize_retire = Methods(self.retire_ports, i=self.layouts.finalize_retire)

        super().__init__(
            {
                "retire_port": Out(
                    RVVIRetireInterface(
                        ilen=gen_params.isa.ilen,
                        xlen=gen_params.isa.xlen,
                        flen=0,
                        vlen=0,
                    ).signature
                ).array(self.retire_ports)
            }
        )

    def elaborate(self, platform):
        m = TModule()

        instr_info_ext = make_layout(
            ("info", self.layouts.instr_info),
            ("priv_mode", PrivilegeLevel),
        )

        m.submodules.ftq_mem = ftq_mem = memory.Memory(
            shape=instr_info_ext, depth=self.gen_params.ftq_size * self.gen_params.fetch_width, init=[]
        )

        m.submodules.rob_mem = rob_mem = memory.Memory(shape=instr_info_ext, depth=self.gen_params.rob_entries, init=[])

        m.submodules.rf_mem = rf_mem = memory.Memory(
            shape=self.gen_params.isa.xlen, depth=self.gen_params.phys_regs, init=[]
        )

        ftq_write_ports = [ftq_mem.write_port() for _ in range(self.gen_params.fetch_width)]
        ftq_read_ports = [ftq_mem.read_port(domain="comb") for _ in range(self.frontend_ports)]
        rob_write_ports = [rob_mem.write_port() for _ in range(self.frontend_ports)]
        rob_read_ports = [rob_mem.read_port(domain="comb") for _ in range(self.retire_ports)]
        rf_write_ports = [rf_mem.write_port() for _ in range(self.reg_write_ports)]
        rf_read_ports = [rf_mem.read_port(domain="comb") for _ in range(self.retire_ports)]

        ixl = {
            32: XlenEncoding.W32,
            64: XlenEncoding.W64,
            128: XlenEncoding.W128,
        }[self.gen_params.isa.xlen]

        order = Signal(64)
        intr_next = Signal()

        csr = DependencyContext.get().get_dependency(CSRInstancesKey())

        @def_method(m, self.register_ftq)
        def _(ftq_ptr, instrs):
            priv_mode = csr.m_mode.priv_mode.read(m)

            for i in range(self.gen_params.fetch_width):
                port = ftq_write_ports[i]

                m.d.av_comb += port.addr.eq(ftq_ptr.ptr * self.gen_params.fetch_width + i)
                m.d.av_comb += port.data.info.eq(instrs[i])
                m.d.av_comb += port.data.priv_mode.eq(priv_mode)
                m.d.comb += port.en.eq(1)

        @def_methods(m, self.register_ftq_rob_assoc)
        def _(i, ftq_ptr, ftq_offset, rob_id):
            rport = ftq_read_ports[i]
            wport = rob_write_ports[i]

            m.d.av_comb += rport.addr.eq(ftq_ptr.ptr * self.gen_params.fetch_width + ftq_offset)
            m.d.av_comb += wport.addr.eq(rob_id)
            m.d.av_comb += wport.data.eq(rport.data)
            m.d.comb += wport.en.eq(1)

        @def_methods(m, self.register_reg_write)
        def _(i, reg_id, reg_val):
            m.d.av_comb += rf_write_ports[i].addr.eq(reg_id)
            m.d.av_comb += rf_write_ports[i].data.eq(reg_val)
            m.d.comb += rf_write_ports[i].en.eq(reg_id != 0)

        @def_methods(m, self.finalize_retire)
        def _(i, rob_id, rl_dst, rp_dst, trap, interrupt):
            port = self.retire_port[i]

            rob_port = rob_read_ports[i]
            m.d.av_comb += rob_port.addr.eq(rob_id)

            m.d.comb += port.valid.eq(1)
            m.d.av_comb += port.order.eq(order + i)

            m.d.av_comb += port.insn.eq(rob_port.data.info.instr)
            m.d.av_comb += port.trap.eq(trap)
            m.d.av_comb += port.debug_mode.eq(0)
            m.d.av_comb += port.intr.eq(intr_next if i == 0 else 0)
            m.d.av_comb += port.halt.eq(0)  # never happens
            m.d.av_comb += port.pc_rdata.eq(rob_port.data.info.pc)
            m.d.av_comb += port.pc_wdata.eq(0)  # not implemented

            rf_port = rf_read_ports[i]
            m.d.av_comb += rf_port.addr.eq(rp_dst)
            m.d.av_comb += [port.x_wdata[k].eq(rf_port.data) for k in range(32)]
            for k in range(1, 32):
                with m.If(k == rl_dst):
                    m.d.av_comb += port.x_wb[k].eq(1)

            # f_* not implemented

            # v_* not implemented

            # csr_* not implemented

            m.d.av_comb += port.lrsc_cancel.eq(0)  # never happens
            m.d.av_comb += port.mode.eq(rob_port.data.priv_mode)
            m.d.av_comb += port.mode_virt.eq(0)  # always 0
            m.d.av_comb += port.ixl.eq(ixl)

            # set order/intr_next to the last retire port
            m.d.sync += order.eq(order + (i + 1))
            m.d.sync += intr_next.eq(interrupt | trap)

        return m


class RVVIAggregator(Component):
    """A module that aggregates multiple RVVIHartCollector modules into a RVVI-TRACE interface."""

    def __init__(self, rvvi_harts: list[RVVIHartCollector]):
        self.rvvi_harts = rvvi_harts

        num_harts = len(rvvi_harts)
        ret_count = max(rvvi_hart.retire_ports for rvvi_hart in rvvi_harts)

        fields = {}

        self.ret_port_signature = RVVIRetireInterface(
            ilen=max(rvvi_hart.gen_params.isa.ilen for rvvi_hart in rvvi_harts),
            xlen=max(rvvi_hart.gen_params.isa.xlen for rvvi_hart in rvvi_harts),
            flen=0,
            vlen=0,
        ).signature

        ret_interface_fields = self.ret_port_signature.members

        for field in ret_interface_fields:
            fields[field] = ret_interface_fields[field].array(num_harts, ret_count)

        super().__init__(fields)

    def elaborate(self, platform):
        m = TModule()

        # TODO: clk signal, but should be always positive edge

        for i, rvvi_hart in enumerate(self.rvvi_harts):
            for j in range(rvvi_hart.retire_ports):
                for field in self.ret_port_signature.members:
                    lhs = getattr(self, field)[i][j]
                    rhs = getattr(rvvi_hart.retire_port[j], field)
                    m.d.comb += lhs.eq(rhs)

        return m
