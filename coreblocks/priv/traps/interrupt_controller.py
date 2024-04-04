from amaranth import *
from amaranth.lib.enum import IntEnum

from coreblocks.frontend.decoder.isa import PrivilegeLevel
from coreblocks.priv.csr.csr_register import CSRRegister
from coreblocks.params.genparams import GenParams
from coreblocks.interface.keys import AsyncInterruptInsertSignalKey, MretKey

from transactron.core import Method, TModule, def_method
from transactron.core.transaction import Transaction
from transactron.utils.dependencies import DependencyManager


class InterruptCauseNumber(IntEnum):
    SSI = 1
    MSI = 3
    STI = 5
    MTI = 7
    SEI = 9
    MEI = 11


# TODO: upgrade to component
class InternalInterruptController(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params
        dm = gen_params.get(DependencyManager)

        # export only bits mxlen-1:16
        self.edge_report_interrupt = Signal(gen_params.isa.xlen)
        self.level_report_interrupt = Signal(gen_params.isa.xlen)
        self.edge_reported_mask = 0
        self.num_custom_interrupts = 0
        if self.num_custom_interrupts > gen_params.isa.xlen - 16:
            raise RuntimeError("Too many custom interrupts")

        # MIE bit - global interrupt enable - part of mstatus CSR
        self.mstatus_mie = CSRRegister(None, gen_params, width=1)
        # MPIE bit - previous MIE - part of mstatus
        self.mstatus_mpie = CSRRegister(None, gen_params, width=1)
        # MPP bit - previous priv mode - part of mstatus
        self.mstatus_mpp = CSRRegister(None, gen_params, width=2, ro_bits=0b11, reset=PrivilegeLevel.MACHINE)
        # TODO: filter xPP for only legal modes (when not read-only)

        mie_writeable = (
            # (1 << InterruptCauseNumber.MSI)
            # (1 << InterruptCauseNumber.MTI)
            (1 << InterruptCauseNumber.MEI)
            | (((1 << self.num_custom_interrupts) - 1) << 16)
        )
        self.mie = CSRRegister(69, gen_params, ro_bits=~mie_writeable)
        self.mip = CSRRegister(70, gen_params, fu_write_priority=False, ro_bits=~self.edge_reported_mask)

        self.interrupt_insert = Signal()
        dm.add_dependency(AsyncInterruptInsertSignalKey(), self.interrupt_insert)

        self.interrupt_cause = Signal(gen_params.isa.xlen)

        self.mret = Method()
        dm.add_dependency(MretKey(), self.mret)

        self.entry = Method()

    def elaborate(self, platform):
        m = TModule()

        m.submodules += [self.mstatus_mie, self.mstatus_mpie, self.mstatus_mpp, self.mie]

        interrupt_enable = self.mstatus_mie.read(m).data
        interrupt_pending = (self.mie.read(m).data & self.mip.read(m).data).any()
        m.d.comb += self.interrupt_insert.eq(interrupt_pending & interrupt_enable)

        with Transaction().body(m):
            # 1. Get MIP CSR write from instruction or previous value
            mip_value = self.mip.read_comb(m).data

            # 2. Apply new egde interrupts (after the FU read-modify-write cycle)
            # This is not standardised by the spec, but makes sense to enforce independent
            # order and don't miss interrupts that happen in the cycle of FU write
            mip_value |= self.edge_report_interrupt

            # 3. Mask with FU read-only level reported interrupts
            mip_value &= self.edge_reported_mask
            mip_value |= self.level_report_interrupt & ~self.edge_report_interrupt

            self.mip.write(m, mip_value)

        @def_method(m, self.mret)
        def _():
            self.mstatus_mie.write(m, self.mstatus_mpie.read(m).data)
            self.mstatus_mpie.write(m, 1)
            # TODO: Set mpp when other privilege modes are implemented

        # mret/entry conflict cannot happen, mret is called under precommit
        @def_method(m, self.entry)
        def _():
            self.mstatus_mie.write(m, 0)
            self.mstatus_mpie.write(m, self.mie.read(m).data)

        interrupt_priority = [
            InterruptCauseNumber.MEI,
            InterruptCauseNumber.MSI,
            InterruptCauseNumber.MTI,
            InterruptCauseNumber.SEI,
            InterruptCauseNumber.SSI,
            InterruptCauseNumber.STI,
        ] + [
            i for i in range(16, self.gen_params.isa.xlen)
        ]  # custom use range

        top_interrupt = Signal(range(self.gen_params.isa.xlen))
        for bit in reversed(interrupt_priority):
            with m.If(self.mip.read(m).data[bit]):
                m.d.comb += top_interrupt.eq(bit)

        # Level-triggered interrupts can disappear after insertion to the instruction core,
        # but they cannot be canceled at this point. Latch last interrupt cause reason that makes
        # sense, in case of every interrupt becoming disabled before reaching the retirement
        # NOTE2: we depend on the fact that writes to xIE stall the fetcher. In other case
        # interrupt could be explicitly disabled, after being irrecoverably inserted to the core.
        with m.If(self.interrupt_insert):
            m.d.sync += self.interrupt_cause.eq(top_interrupt)

        return m
