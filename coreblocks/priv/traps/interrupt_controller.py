from amaranth import *
from amaranth.lib.enum import IntEnum
from amaranth.lib.wiring import Component, In, Signature

from coreblocks.frontend.decoder.isa import PrivilegeLevel
from coreblocks.interface.layouts import InternalInterruptControllerLayouts
from coreblocks.priv.csr.csr_register import CSRRegister
from coreblocks.priv.csr.csr_instances import CSRAddress
from coreblocks.params.genparams import GenParams
from coreblocks.interface.keys import AsyncInterruptInsertSignalKey, GenericCSRRegistersKey, MretKey

from transactron.core import Method, TModule, def_method
from transactron.core.transaction import Transaction
from transactron.core.transaction_base import Priority
from transactron.utils.dependencies import DependencyManager


class InterruptCauseNumber(IntEnum):
    SSI = 1
    MSI = 3
    STI = 5
    MTI = 7
    SEI = 9
    MEI = 11


ISA_RESERVED_INTERRUPTS = 16


class InternalInterruptControllerSignature(Signature):
    def __init__(self, gen_params: GenParams):
        super().__init__(
            {
                "internal_report_level": In(ISA_RESERVED_INTERRUPTS),
                "custom_report_level": In(gen_params.interrupt_custom_count),
                "custom_report_edge": In(gen_params.interrupt_custom_count),
            }
        )


class InternalInterruptController(Component):
    internal_report_level: Signal
    custom_report_level: Signal
    custom_report_edge: Signal

    def __init__(self, gen_params: GenParams):
        super().__init__(InternalInterruptControllerSignature(gen_params))

        self.gen_params = gen_params
        dm = gen_params.get(DependencyManager)

        self.edge_reported_mask = self.gen_params.interrupt_custom_edge_trig_mask << ISA_RESERVED_INTERRUPTS
        if gen_params.interrupt_custom_count > gen_params.isa.xlen - ISA_RESERVED_INTERRUPTS:
            raise RuntimeError("Too many custom interrupts")

        # MIE bit - global interrupt enable - part of mstatus CSR
        self.mstatus_mie = CSRRegister(None, gen_params, width=1)
        # MPIE bit - previous MIE - part of mstatus
        self.mstatus_mpie = CSRRegister(None, gen_params, width=1)
        # MPP bit - previous priv mode - part of mstatus
        self.mstatus_mpp = CSRRegister(None, gen_params, width=2, ro_bits=0b11, reset=PrivilegeLevel.MACHINE)
        # TODO: filter xPP for only legal modes (when not read-only)
        mstatus = dm.get_dependency(GenericCSRRegistersKey()).m_mode.mstatus
        mstatus.add_field(3, self.mstatus_mie)
        mstatus.add_field(7, self.mstatus_mpie)
        mstatus.add_field(11, self.mstatus_mpp)

        mie_writeable = (
            # (1 << InterruptCauseNumber.MSI)
            # (1 << InterruptCauseNumber.MTI)
            (1 << InterruptCauseNumber.MEI)
            | (((1 << gen_params.interrupt_custom_count) - 1) << 16)
        )
        self.mie = CSRRegister(CSRAddress.MIE, gen_params, ro_bits=~mie_writeable)
        self.mip = CSRRegister(CSRAddress.MIP, gen_params, fu_write_priority=False, ro_bits=~self.edge_reported_mask)

        self.interrupt_insert = Signal()
        dm.add_dependency(AsyncInterruptInsertSignalKey(), self.interrupt_insert)

        self.interrupt_cause = Method(o=gen_params.get(InternalInterruptControllerLayouts).interrupt_cause)

        self.mret = Method()
        dm.add_dependency(MretKey(), self.mret)

        self.entry = Method()

    def elaborate(self, platform):
        m = TModule()

        interrupt_cause = Signal(self.gen_params.isa.xlen)

        m.submodules += [self.mstatus_mie, self.mstatus_mpie, self.mstatus_mpp, self.mie, self.mip]

        interrupt_enable = Signal()
        mie = Signal(self.gen_params.isa.xlen)
        mip = Signal(self.gen_params.isa.xlen)
        with Transaction().body(m):
            m.d.comb += [
                interrupt_enable.eq(self.mstatus_mie.read(m).data),
                mie.eq(self.mie.read(m).data),
                mip.eq(self.mip.read(m).data),
            ]

        interrupt_pending = (mie & mip).any()
        m.d.comb += self.interrupt_insert.eq(interrupt_pending & interrupt_enable)

        edge_report_interrupt = Signal(self.gen_params.isa.xlen)
        level_report_interrupt = Signal(self.gen_params.isa.xlen)
        m.d.comb += edge_report_interrupt.eq(self.custom_report_edge << ISA_RESERVED_INTERRUPTS)
        m.d.comb += level_report_interrupt.eq(
            (self.custom_report_level << ISA_RESERVED_INTERRUPTS) | self.internal_report_level
        )

        with Transaction().body(m):
            # 1. Get MIP CSR write from instruction or previous value
            mip_value = self.mip.read_comb(m).data

            # 2. Apply new egde interrupts (after the FU read-modify-write cycle)
            # This is not standardised by the spec, but makes sense to enforce independent
            # order and don't miss interrupts that happen in the cycle of FU write
            mip_value |= edge_report_interrupt

            # 3. Mask with FU read-only level reported interrupts
            mip_value &= self.edge_reported_mask
            mip_value |= level_report_interrupt & ~self.edge_reported_mask

            self.mip.write(m, {"data": mip_value})  # ????

        @def_method(m, self.mret)
        def _():
            pass

        @def_method(m, self.entry)
        def _():
            pass

        # mret/entry conflict cannot happen (mret under precommit)
        # comment here
        with Transaction().body(m):
            with m.If(self.entry.run):
                self.mstatus_mie.write(m, {"data": 0})
                self.mstatus_mpie.write(m, self.mstatus_mie.read(m).data)
            with m.Elif(self.mret.run):
                self.mstatus_mie.write(m, self.mstatus_mpie.read(m).data)
                self.mstatus_mpie.write(m, {"data": 1})
                # TODO: Set mpp when other privilege modes are implemented

        interrupt_priority = [
            InterruptCauseNumber.MEI,
            InterruptCauseNumber.MSI,
            InterruptCauseNumber.MTI,
            InterruptCauseNumber.SEI,
            InterruptCauseNumber.SSI,
            InterruptCauseNumber.STI,
        ] + [
            i for i in range(16, 16 + self.gen_params.interrupt_custom_count)
        ]  # custom use range

        top_interrupt = Signal(range(self.gen_params.isa.xlen))
        for bit in reversed(interrupt_priority):
            with m.If(mip[bit] & mie[bit]):
                m.d.comb += top_interrupt.eq(bit)

        # Level-triggered interrupts can disappear after insertion to the instruction core,
        # but they cannot be canceled at this point. Latch last interrupt cause reason that makes
        # sense, in case of every interrupt becoming disabled before reaching the retirement
        # NOTE2: we depend on the fact that writes to xIE stall the fetcher. In other case
        # interrupt could be explicitly disabled, after being irrecoverably inserted to the core.
        with m.If(self.interrupt_insert):
            m.d.sync += interrupt_cause.eq(top_interrupt)

        @def_method(m, self.interrupt_cause)
        def _():
            return {"cause": interrupt_cause}

        return m
