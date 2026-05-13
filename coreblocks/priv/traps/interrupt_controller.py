from amaranth import *
from amaranth.lib.wiring import Component, In

from coreblocks.arch import CSRAddress, InterruptCauseNumber, PrivilegeLevel
from coreblocks.arch.isa_consts import ExceptionCause
from coreblocks.interface.layouts import InternalInterruptControllerLayouts
from coreblocks.priv.csr.csr_register import CSRRegister
from coreblocks.priv.csr.shadow import ShadowCSR
from coreblocks.params.genparams import GenParams
from coreblocks.interface.keys import (
    AsyncInterruptInsertSignalKey,
    CSRInstancesKey,
    MretKey,
    SretKey,
    WaitForInterruptResumeKey,
)

from transactron.core import Method, TModule, def_method
from transactron.core.transaction import Transaction
from transactron.utils import logging
from transactron.utils.dependencies import DependencyContext
from transactron.lib.transformers import MethodMap

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

        self.level_interrupts = Signal(self.gen_params.isa.xlen)
        self.new_edge_interrupts = Signal(self.gen_params.isa.xlen)

        self.m_mode_csr = m_mode_csr = self.dm.get_dependency(CSRInstancesKey()).m_mode
        self.mstatus_mie = m_mode_csr.mstatus_mie
        self.mstatus_mpie = m_mode_csr.mstatus_mpie
        self.mstatus_mpp = m_mode_csr.mstatus_mpp
        self.mstatus_sie = m_mode_csr.mstatus_sie
        self.mstatus_spie = m_mode_csr.mstatus_spie
        self.mstatus_spp = m_mode_csr.mstatus_spp

        self.mie_writeable = (
            (1 << InterruptCauseNumber.MSI)
            | (1 << InterruptCauseNumber.MTI)
            | (1 << InterruptCauseNumber.MEI)
            | (((1 << gen_params.interrupt_custom_count) - 1) << 16)
        )

        # mip_meip_rdonly
        # mip_mtip_rdonly
        # mip_msip_rdonly
        self.mip_writeable = self.edge_reported_mask

        if gen_params.supervisor_mode:
            # mip_stip_no_stimecmp_acc
            # mip_ssip_acc
            # mip_seip_acc
            self.mip_writeable |= (
                (1 << InterruptCauseNumber.STI) | (1 << InterruptCauseNumber.SSI) | (1 << InterruptCauseNumber.SEI)
            )

        self.mideleg_writeable = (
            (1 << InterruptCauseNumber.SSI)
            | (1 << InterruptCauseNumber.STI)
            | (1 << InterruptCauseNumber.SEI)
            | (((1 << gen_params.interrupt_custom_count) - 1) << 16)
        )

        if gen_params.interrupt_all_interrupts_delegable:
            self.mideleg_writeable |= self.mie_writeable

        # sip_stip_acc
        # sip_seip_acc
        # sip_ssip_acc
        self.sip_writeable = (self.mideleg_writeable & self.edge_reported_mask) | (1 << InterruptCauseNumber.SSI)

        if gen_params.supervisor_mode:
            self.mie_writeable |= self.mideleg_writeable

        assert self.mip_writeable & ~self.mie_writeable == 0
        assert self.sip_writeable & ~self.mideleg_writeable == 0

        if gen_params.supervisor_mode:
            assert self.sip_writeable & ~self.mip_writeable == 0

        self.mie = CSRRegister(CSRAddress.MIE, gen_params, ro_bits=~self.mie_writeable)

        def mip_readmap(m, arg):
            out_data = Signal(self.gen_params.isa.xlen)
            m.d.comb += out_data.eq(arg | self.level_interrupts)
            return out_data

        # NOTE: the mip register only holds bits that are set - either edge triggered or software bits
        # if a bit is both software and level triggered (e.g. STIP), the software will read it as an OR of the two,
        # but the level value will not be participating in the CSRRS/CSRRC logic.
        self.mip = CSRRegister(
            CSRAddress.MIP, gen_params, fu_write_priority=False, ro_bits=~self.mip_writeable, fu_read_map=mip_readmap
        )

        if gen_params.supervisor_mode:
            self.mideleg = CSRRegister(CSRAddress.MIDELEG, gen_params, ro_bits=~self.mideleg_writeable)

            smode_delegable = ExceptionCause.smode_delegable_mask(gen_params.isa.xlen)

            self.medeleg = CSRRegister(CSRAddress.MEDELEG, gen_params, ro_bits=~smode_delegable)
            self.medelegh = None
            if gen_params.isa.xlen == 32:
                self.medelegh = CSRRegister(CSRAddress.MEDELEGH, gen_params, ro_bits=~(smode_delegable >> 32))

            self.sie = ShadowCSR(CSRAddress.SIE, gen_params, self.mie, mask=self.mideleg.read)

            def sip_write_mask_transform(m, arg):
                return {"data": arg.data & self.sip_writeable}

            self.sip_write_mask = MethodMap.create(
                self.mideleg.read,
                o_transform=([("data", self.gen_params.isa.xlen)], sip_write_mask_transform),
            )
            self.sip = ShadowCSR(
                CSRAddress.SIP,
                gen_params,
                self.mip,
                read_mask=self.mideleg.read,
                write_mask=self.sip_write_mask.method,
            )

        self.interrupt_insert = Signal()
        self.dm.add_dependency(AsyncInterruptInsertSignalKey(), self.interrupt_insert)

        self.wfi_resume = Signal()
        self.dm.add_dependency(WaitForInterruptResumeKey(), self.wfi_resume)

        internal_layouts = gen_params.get(InternalInterruptControllerLayouts)
        self.interrupt_cause = Method(o=internal_layouts.interrupt_cause)

        self.mret = Method()
        self.dm.add_dependency(MretKey(), self.mret)

        self.entry = Method(i=[("cause", gen_params.isa.xlen)], o=[("target_priv", PrivilegeLevel)])

        if gen_params.supervisor_mode:
            self.sret = Method()
            self.dm.add_dependency(SretKey(), self.sret)

    def elaborate(self, platform):
        m = TModule()

        interrupt_cause = Signal(self.gen_params.isa.xlen)

        m.submodules += [self.mie, self.mip]

        if self.gen_params.supervisor_mode:
            m.submodules += [self.sie, self.sip, self.mideleg, self.medeleg, self.sip_write_mask]
            if self.medelegh is not None:
                m.submodules += [self.medelegh]

        priv_mode = self.dm.get_dependency(CSRInstancesKey()).m_mode.priv_mode

        interrupt_enable_m = Signal()
        interrupt_enable_s = Signal()
        pending_m = Signal(self.gen_params.isa.xlen)
        pending_s = Signal(self.gen_params.isa.xlen)
        selected_pending = Signal(self.gen_params.isa.xlen)
        interrupt_pending = Signal()

        all_interrupts = Cat(
            self.internal_report_level,
            self.custom_report,
        )
        for i in range(ISA_RESERVED_INTERRUPTS + self.gen_params.interrupt_custom_count):
            if self.edge_reported_mask & (1 << i):
                m.d.comb += self.new_edge_interrupts[i].eq(all_interrupts[i])
            else:
                m.d.comb += self.level_interrupts[i].eq(all_interrupts[i])

        mie = Signal(self.gen_params.isa.xlen)
        mip = Signal(self.gen_params.isa.xlen)
        with Transaction().body(m) as assign_trans:
            priv = priv_mode.read(m).data
            pending = Signal(self.gen_params.isa.xlen)
            mideleg = Signal(self.gen_params.isa.xlen)

            m.d.av_comb += [
                mie.eq(self.mie.read(m).data),
                mip.eq(self.mip.read(m).data | self.level_interrupts),
                pending.eq(mie & mip),
                interrupt_pending.eq(pending.any()),
            ]

            if self.gen_params.supervisor_mode:
                m.d.av_comb += mideleg.eq(self.mideleg.read(m).data)
                m.d.av_comb += [
                    pending_m.eq(pending & ~mideleg),
                    pending_s.eq(pending & mideleg),
                    interrupt_enable_s.eq(
                        ((priv == PrivilegeLevel.SUPERVISOR) & self.mstatus_sie.read(m).data)
                        | (priv < PrivilegeLevel.SUPERVISOR)
                    ),
                ]
            else:
                m.d.av_comb += [
                    pending_m.eq(pending),
                    pending_s.eq(0),
                    interrupt_enable_s.eq(0),
                ]

            m.d.av_comb += interrupt_enable_m.eq(self.mstatus_mie.read(m).data | (priv < PrivilegeLevel.MACHINE))
        log.error(m, ~assign_trans.run, "assert transaction running failed")

        m_interrupt_insert = Signal()
        s_interrupt_insert = Signal()

        m.d.comb += [
            m_interrupt_insert.eq(pending_m.any() & interrupt_enable_m),
            s_interrupt_insert.eq(pending_s.any() & interrupt_enable_s),
            self.interrupt_insert.eq(m_interrupt_insert | s_interrupt_insert),
        ]

        m.d.comb += selected_pending.eq(Mux(m_interrupt_insert, pending_m, pending_s))

        # WFI is independent of global mstatus.xIE and mideleg
        m.d.comb += self.wfi_resume.eq(interrupt_pending)

        with Transaction().body(m) as mip_trans:
            mip_value = self.mip.read_comb(m).data
            new_data = Signal(self.gen_params.isa.xlen)
            m.d.av_comb += new_data.eq(mip_value | self.new_edge_interrupts)
            self.mip.write(m, {"data": new_data})
        log.error(m, ~mip_trans.run, "assert transaction running failed")

        @def_method(m, self.mret)
        def _():
            log.info(m, True, "Interrupt handler return")

        if self.gen_params.supervisor_mode:

            @def_method(m, self.sret)
            def _():
                log.info(m, True, "Supervisor interrupt handler return")

        @def_method(m, self.entry)
        def _(cause):
            cause_num = Signal(self.gen_params.isa.xlen - 1)
            is_interrupt = Signal()
            m.d.av_comb += Cat(cause_num, is_interrupt).eq(cause)

            target_priv = Signal(PrivilegeLevel, init=PrivilegeLevel.MACHINE)

            if self.gen_params.supervisor_mode:
                with m.If(is_interrupt):
                    ideleg = self.mideleg.read(m).data
                    m.d.av_comb += target_priv.eq(
                        Mux(ideleg.bit_select(cause_num, 1), PrivilegeLevel.SUPERVISOR, PrivilegeLevel.MACHINE)
                    )
                with m.Else():
                    edeleg = Signal(64)

                    if self.medelegh is not None:
                        m.d.av_comb += edeleg.eq(Cat(self.medeleg.read(m).data, self.medelegh.read(m).data))
                    else:
                        m.d.av_comb += edeleg.eq(self.medeleg.read(m).data)

                    with m.If(priv_mode.read(m).data < PrivilegeLevel.MACHINE):
                        m.d.av_comb += target_priv.eq(
                            Mux(edeleg.bit_select(cause_num, 1), PrivilegeLevel.SUPERVISOR, PrivilegeLevel.MACHINE)
                        )
                    with m.Else():
                        m.d.av_comb += target_priv.eq(PrivilegeLevel.MACHINE)

            log.info(m, True, "Interrupt handler entry to {}", target_priv)
            return {"target_priv": target_priv}

        # mret/sret/entry conflicts cannot happen in real conditions - xret is called under precommit
        # this is split here to avoid complicated call graphs and conflicts that are not handled well by Transactron
        with Transaction().body(m):
            with m.If(self.entry.run):
                priv = priv_mode.read(m).data
                target_priv = self.entry.data_out.target_priv
                log.assertion(m, target_priv >= priv, "Trap must not decrease privilege levels")
                with m.Switch(target_priv):
                    if self.gen_params.supervisor_mode:
                        with m.Case(PrivilegeLevel.SUPERVISOR):
                            log.info(m, True, "Entering supervisor interrupt handler")
                            self.mstatus_sie.write(m, {"data": 0})
                            self.mstatus_spie.write(m, self.mstatus_sie.read(m).data)
                            self.mstatus_spp.write(m, priv != PrivilegeLevel.USER)
                            priv_mode.write(m, PrivilegeLevel.SUPERVISOR)
                    with m.Case(PrivilegeLevel.MACHINE):
                        log.info(m, True, "Entering machine interrupt handler")
                        self.mstatus_mie.write(m, {"data": 0})
                        self.mstatus_mpie.write(m, self.mstatus_mie.read(m).data)
                        self.mstatus_mpp.write(m, priv)
                        priv_mode.write(m, PrivilegeLevel.MACHINE)
            with m.Elif(self.mret.run):
                self.mstatus_mie.write(m, self.mstatus_mpie.read(m).data)
                self.mstatus_mpie.write(m, {"data": 1})
                self.mstatus_mpp.write(m, PrivilegeLevel.USER if self.gen_params.user_mode else PrivilegeLevel.MACHINE)
                mpp = self.mstatus_mpp.read(m).data
                priv_mode.write(m, mpp)
                with m.If(mpp != PrivilegeLevel.MACHINE):
                    self.m_mode_csr.mstatus_mprv.write(m, 0)
            if self.gen_params.supervisor_mode:
                with m.Elif(self.sret.run):
                    self.mstatus_sie.write(m, self.mstatus_spie.read(m).data)
                    self.mstatus_spie.write(m, {"data": 1})
                    self.mstatus_spp.write(m, 0)
                    spp = self.mstatus_spp.read(m).data
                    priv_mode.write(m, Mux(spp, PrivilegeLevel.SUPERVISOR, PrivilegeLevel.USER))
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
            with m.If(selected_pending[bit]):
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
