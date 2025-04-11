from amaranth import *
from amaranth.lib.wiring import Component, In

from coreblocks.arch import CSRAddress, InterruptCauseNumber, PrivilegeLevel
from coreblocks.interface.layouts import InternalInterruptControllerLayouts
from coreblocks.priv.csr.csr_register import CSRRegister
from coreblocks.params.genparams import GenParams
from coreblocks.interface.keys import (
    AsyncInterruptInsertSignalKey,
    CSRInstancesKey,
    MretKey,
    WaitForInterruptResumeKey,
)

from transactron.core import Method, TModule, def_method
from transactron.core.transaction import Transaction
from transactron.lib import logging
from transactron.utils.dependencies import DependencyContext


log = logging.HardwareLogger("core.interrupt_controller")


ISA_RESERVED_INTERRUPTS = 16


class InternalInterruptController(Component):
    """Core Internal Interrupt Controller
    Compatible with RISC-V privileged specification.
    Operates on CSR registers xIE, xIP, and parts of xSTATUS.
    Interrups are reported via plain signals in Component interface.

    Attributes
    ----------
    internal_report_level: In, 16
        Level-triggered input for interrupts with numbers 0-15, assigned by spec for standard interrupts (internal use)
    custom_report: In, interrupt_custom_count
        Input for reporting custom/local interrupts starting with number 16.
        Each custom interrupt can be either level-triggered or edge-triggered, configured by `CoreConfiguration`.
        See `interrupt_custom_count` and `interrupt_custom_edge_trig_mask` in `CoreConfiguration`.
    interrupt_insert: Out, 1
        Internal interface, signals pending interrupt.
    entry: Method
        Internal interface, changes state to interrupt handler entry.
    mret: Method
        Internal interface, changes state to interrupt handler exit.
    interrupt_cause: Method
        Internal interface, provides number of the most prioritized interrupt that caused current interrupt insertion.
    """

    internal_report_level: Signal
    custom_report: Signal

    def __init__(self, gen_params: GenParams):
        super().__init__(
            {
                "internal_report_level": In(ISA_RESERVED_INTERRUPTS),
                "custom_report": In(gen_params.interrupt_custom_count),
            }
        )

        self.gen_params = gen_params
        self.dm = DependencyContext.get()

        self.edge_reported_mask = self.gen_params.interrupt_custom_edge_trig_mask << ISA_RESERVED_INTERRUPTS
        if gen_params.interrupt_custom_count > gen_params.isa.xlen - ISA_RESERVED_INTERRUPTS:
            raise RuntimeError("Too many custom interrupts")

        self.m_mode_csr = m_mode_csr = self.dm.get_dependency(CSRInstancesKey()).m_mode
        self.mstatus_mie = m_mode_csr.mstatus_mie
        self.mstatus_mpie = m_mode_csr.mstatus_mpie
        self.mstatus_mpp = m_mode_csr.mstatus_mpp

        mie_writeable = (
            # (1 << InterruptCauseNumber.MSI) TODO: CLINT
            # (1 << InterruptCauseNumber.MTI) TODO: CLINT
            (1 << InterruptCauseNumber.MEI)
            | (((1 << gen_params.interrupt_custom_count) - 1) << 16)
        )
        self.mie = CSRRegister(CSRAddress.MIE, gen_params, ro_bits=~mie_writeable)
        self.mip = CSRRegister(CSRAddress.MIP, gen_params, fu_write_priority=False, ro_bits=~self.edge_reported_mask)

        self.interrupt_insert = Signal()
        self.dm.add_dependency(AsyncInterruptInsertSignalKey(), self.interrupt_insert)

        self.wfi_resume = Signal()
        self.dm.add_dependency(WaitForInterruptResumeKey(), self.wfi_resume)

        self.interrupt_cause = Method(o=gen_params.get(InternalInterruptControllerLayouts).interrupt_cause)

        self.mret = Method()
        self.dm.add_dependency(MretKey(), self.mret)

        self.entry = Method()

    def elaborate(self, platform):
        m = TModule()

        interrupt_cause = Signal(self.gen_params.isa.xlen)

        m.submodules += [self.mie, self.mip]

        priv_mode = self.dm.get_dependency(CSRInstancesKey()).m_mode.priv_mode

        interrupt_enable = Signal()
        mie = Signal(self.gen_params.isa.xlen)
        mip = Signal(self.gen_params.isa.xlen)
        with Transaction().body(m) as assign_trans:
            m.d.comb += [
                interrupt_enable.eq(self.mstatus_mie.read(m).data | (priv_mode.read(m).data == PrivilegeLevel.USER)),
                mie.eq(self.mie.read(m).data),
                mip.eq(self.mip.read(m).data),
            ]
        log.error(m, ~assign_trans.grant, "assert transaction running failed")

        interrupt_pending = (mie & mip).any()
        m.d.comb += self.interrupt_insert.eq(interrupt_pending & interrupt_enable)

        # WFI is independent of global mstatus.xIE and mideleg
        m.d.comb += self.wfi_resume.eq(interrupt_pending)

        edge_report_interrupt = Signal(self.gen_params.isa.xlen)
        level_report_interrupt = Signal(self.gen_params.isa.xlen)
        m.d.comb += edge_report_interrupt.eq((self.custom_report << ISA_RESERVED_INTERRUPTS) & self.edge_reported_mask)
        m.d.comb += level_report_interrupt.eq(
            ((self.custom_report << ISA_RESERVED_INTERRUPTS) & ~self.edge_reported_mask) | self.internal_report_level
        )

        with Transaction().body(m) as mip_trans:
            # 1. Get MIP CSR write from instruction or previous value
            mip_value = self.mip.read_comb(m).data

            # 2. Apply new egde interrupts (after the FU read-modify-write cycle)
            # This is not standardised by the spec, but makes sense to enforce independent
            # order and don't miss interrupts that happen in the cycle of FU write
            mip_value |= edge_report_interrupt

            # 3. Mask with FU read-only level reported interrupts
            mip_value &= self.edge_reported_mask
            mip_value |= level_report_interrupt & ~self.edge_reported_mask

            self.mip.write(m, {"data": mip_value})
        log.error(m, ~mip_trans.grant, "assert transaction running failed")

        @def_method(m, self.mret)
        def _():
            log.info(m, True, "Interrupt handler return")
            pass

        @def_method(m, self.entry)
        def _():
            log.info(m, True, "Interrupt handler entry")
            pass

        # mret/entry conflict cannot happen in real conditons - mret is called under precommit
        # it is split here to avoid complicated call graphs and conflicts that are not handled well by Transactron
        with Transaction().body(m):
            with m.If(self.entry.run):
                self.mstatus_mie.write(m, {"data": 0})
                self.mstatus_mpie.write(m, self.mstatus_mie.read(m).data)
                self.mstatus_mpp.write(m, priv_mode.read(m).data)
                priv_mode.write(m, PrivilegeLevel.MACHINE)
            with m.Elif(self.mret.run):
                self.mstatus_mie.write(m, self.mstatus_mpie.read(m).data)
                self.mstatus_mpie.write(m, {"data": 1})
                self.mstatus_mpp.write(m, PrivilegeLevel.USER if self.gen_params.user_mode else PrivilegeLevel.MACHINE)
                mpp = self.mstatus_mpp.read(m).data
                priv_mode.write(m, mpp)
                with m.If(mpp != PrivilegeLevel.MACHINE):
                    self.m_mode_csr.mstatus_mprv.write(m, 0)

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
