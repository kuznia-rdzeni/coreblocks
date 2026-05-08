from amaranth import *
from amaranth.lib.enum import Enum, unique, auto

from transactron import Method, TModule, def_method, Transaction
from transactron.lib import Forwarder, condition
from transactron.utils import DependencyContext, make_layout, HardwareLogger

from coreblocks.arch.isa_consts import PrivilegeLevel, SatpMode, PAGE_SIZE_LOG
from coreblocks.interface.keys import CSRInstancesKey, L1TLBBackingDeviceKey
from coreblocks.interface.layouts import AddressTranslationLayouts
from coreblocks.params import GenParams

from coreblocks.priv.vmem.tlb import FullyAssociativeTLB


__all__ = ["AddressTranslator", "AddressTranslatorMode"]


log = HardwareLogger("mmu.translation")


@unique
class AddressTranslatorMode(Enum):
    INSTRUCTION = auto()
    LSU = auto()


class AddressTranslator(Elaboratable):
    """Address translator from virtual to physical addresses."""

    def __init__(
        self,
        gen_params: GenParams,
        *,
        mode: AddressTranslatorMode,
    ) -> None:
        self.gen_params = gen_params
        self.mode = mode
        self.layouts = self.gen_params.get(AddressTranslationLayouts)

        self.request = Method(i=self.layouts.request)
        self.accept = Method(o=self.layouts.accept)

        self.dm = DependencyContext.get()

        self.tlb = None
        if gen_params.vmem_params.supported_non_bare_schemes:
            self.tlb = FullyAssociativeTLB(
                gen_params,
                entries=(
                    gen_params.tlb_config.itlb_entries
                    if mode == AddressTranslatorMode.INSTRUCTION
                    else gen_params.tlb_config.dtlb_entries
                ),
                backing_resolver=self.dm.get_dependency(L1TLBBackingDeviceKey()),
            )

    def elaborate(self, platform):
        m = TModule()

        bits_per_level = SatpMode.bits_per_page_table_level(self.gen_params.isa.xlen)

        fwd_layout = make_layout(
            ("vaddr", self.gen_params.isa.xlen),
            ("access_fault", 1),
            ("vpn_invalid", 1),
            ("write_aspect", 1),
        )
        m.submodules.resp_fwd = resp_fwd = Forwarder(fwd_layout)

        if self.tlb is not None:
            m.submodules.tlb = self.tlb

        csr = self.dm.get_dependency(CSRInstancesKey())

        effective_priv_mode = Signal(PrivilegeLevel, init=PrivilegeLevel.MACHINE)
        effective_satp_mode = Signal(SatpMode, init=SatpMode.BARE)

        mxr = Signal()
        sum_ = Signal()

        with Transaction().body(m) as t:
            priv_mode = csr.m_mode.priv_mode.read(m).data

            match self.mode:
                case AddressTranslatorMode.LSU:
                    mprv = csr.m_mode.mstatus_mprv.read(m).data
                    mpp = csr.m_mode.mstatus_mpp.read(m).data

                    m.d.av_comb += effective_priv_mode.eq(Mux(mprv, mpp, priv_mode))

                case AddressTranslatorMode.INSTRUCTION:
                    m.d.av_comb += effective_priv_mode.eq(priv_mode)

            if self.gen_params.supervisor_mode:
                with m.If(effective_priv_mode < PrivilegeLevel.MACHINE):
                    m.d.av_comb += effective_satp_mode.eq(csr.s_mode.satp_mode)

            m.d.av_comb += mxr.eq(csr.m_mode.mstatus_mxr.read(m).data)
            m.d.av_comb += sum_.eq(csr.m_mode.mstatus_sum.read(m).data)

        log.error(m, ~t.run, "Transaction must always run")

        @def_method(m, self.request)
        def _(addr: Value, write_aspect: Value):
            access_fault = Signal()
            vpn_invalid = Signal()

            poffset = Signal(PAGE_SIZE_LOG)
            vpn = Signal(self.gen_params.isa.xlen - PAGE_SIZE_LOG)

            max_ppn = (1 << (self.gen_params.phys_addr_bits - PAGE_SIZE_LOG)) - 1

            m.d.av_comb += Cat(poffset, vpn).eq(addr)

            with m.Switch(effective_satp_mode):
                with m.Case(SatpMode.BARE):
                    m.d.av_comb += access_fault.eq(vpn > max_ppn)

                for vm_mode in self.gen_params.vmem_params.supported_non_bare_schemes:
                    vm_vpn_len = bits_per_level * SatpMode.level_count(vm_mode)

                    with m.Case(vm_mode):
                        m.d.av_comb += vpn_invalid.eq(vpn[vm_vpn_len - 1 :].any() & ~vpn[vm_vpn_len - 1 :].all())

            if self.tlb is not None:
                with m.If((effective_satp_mode != SatpMode.BARE) & ~vpn_invalid):
                    self.tlb.request(
                        m,
                        vpn=vpn,
                        write_aspect=write_aspect,
                    )

            resp_fwd.write(
                m,
                vaddr=addr,
                vpn_invalid=vpn_invalid,
                access_fault=access_fault,
                write_aspect=write_aspect,
            )

        @def_method(m, self.accept)
        def _():
            ppn = Signal(self.gen_params.phys_addr_bits - PAGE_SIZE_LOG)
            page_fault = Signal()
            access_fault = Signal()

            data = resp_fwd.read(m)
            tlb_data = Signal(self.layouts.tlb_accept)

            vpn = Signal(self.gen_params.isa.xlen - PAGE_SIZE_LOG)
            poffset = Signal(PAGE_SIZE_LOG)

            m.d.av_comb += Cat(poffset, vpn).eq(data.vaddr)

            with m.If(data.access_fault):
                m.d.av_comb += access_fault.eq(1)

            with m.If(data.vpn_invalid):
                m.d.av_comb += page_fault.eq(1)

            if self.tlb is not None:
                with condition(m, nonblocking=True) as branch:
                    with branch((effective_satp_mode != SatpMode.BARE) & ~data.vpn_invalid):
                        m.d.av_comb += tlb_data.eq(self.tlb.accept(m))

            with m.If(effective_satp_mode == SatpMode.BARE):
                m.d.av_comb += ppn.eq(vpn)
            with m.Else():
                with m.Switch(tlb_data.result):
                    with m.Case(AddressTranslationLayouts.TLBResult.HIT):
                        with m.If(data.write_aspect):
                            log.assertion(
                                m, tlb_data.permissions.d, "TLB entry must have dirty bit set if we are writing"
                            )
                    with m.Case(AddressTranslationLayouts.TLBResult.PAGE_FAULT):
                        m.d.av_comb += page_fault.eq(1)
                    with m.Case(AddressTranslationLayouts.TLBResult.ACCESS_FAULT):
                        m.d.av_comb += access_fault.eq(1)

                # apply lower bits from VPN if we have hit a superpage
                with m.Switch(tlb_data.size_class):
                    for size_class in range(self.gen_params.vmem_params.max_tlb_size_class + 1):
                        level_bits = bits_per_level * size_class
                        with m.Case(size_class):
                            m.d.av_comb += ppn.eq(Cat(vpn[:level_bits], tlb_data.ppn[level_bits:]))

                # check RWX permissions
                match self.mode:
                    case AddressTranslatorMode.INSTRUCTION:
                        log.assertion(m, ~data.write_aspect, "Instruction fetch cannot have write aspect")

                        with m.If(~tlb_data.permissions.x):
                            m.d.av_comb += page_fault.eq(1)
                    case AddressTranslatorMode.LSU:
                        with m.If(data.write_aspect):
                            with m.If(~tlb_data.permissions.w):
                                m.d.av_comb += page_fault.eq(1)
                        with m.Else():
                            with m.If(~tlb_data.permissions.r & ~(mxr & tlb_data.permissions.x)):
                                m.d.av_comb += page_fault.eq(1)

                # check U/S permissions
                is_user = effective_priv_mode == PrivilegeLevel.USER
                match self.mode:
                    case AddressTranslatorMode.INSTRUCTION:
                        # SUM does not affect instruction fetches
                        with m.If(is_user != tlb_data.permissions.u):
                            m.d.av_comb += page_fault.eq(1)
                    case AddressTranslatorMode.LSU:
                        with m.If(is_user):
                            with m.If(~tlb_data.permissions.u):
                                m.d.av_comb += page_fault.eq(1)
                        with m.Else():
                            with m.If(tlb_data.permissions.u & ~sum_):
                                m.d.av_comb += page_fault.eq(1)

            return {
                "vaddr": data.vaddr,
                "paddr": Cat(poffset, ppn),
                "page_fault": page_fault,
                "access_fault": access_fault,
            }

        return m
