from amaranth import *
from amaranth.lib.data import StructLayout
from amaranth.lib.enum import Enum, unique, auto

from transactron import Method, TModule, def_method
from transactron.lib import Forwarder
from transactron.utils import DependencyContext

from coreblocks.arch.isa_consts import PrivilegeLevel, SatpMode, PAGE_SIZE, PAGE_SIZE_LOG
from coreblocks.interface.keys import CSRInstancesKey
from coreblocks.interface.layouts import AddressTranslationLayouts
from coreblocks.params import GenParams

__all__ = ["AddressTranslator", "AddressTranslatorMode"]


@unique
class AddressTranslatorMode(Enum):
    INSTRUCTION = auto()
    LSU = auto()


def level_count(mode: SatpMode) -> int:
    match mode:
        case SatpMode.BARE:
            return 0
        case SatpMode.SV32:
            return 2
        case SatpMode.SV39:
            return 3
        case SatpMode.SV48:
            return 4
        case SatpMode.SV57:
            return 5
        case _:
            raise ValueError(f"Unsupported SATP mode: {mode}")


def page_table_entry_format(mode: SatpMode) -> StructLayout:
    match mode:
        case SatpMode.BARE:
            return StructLayout({})
        case SatpMode.SV32:
            return StructLayout(
                {
                    "V": 1,
                    "R": 1,
                    "W": 1,
                    "X": 1,
                    "U": 1,
                    "G": 1,
                    "A": 1,
                    "D": 1,
                    "RSW": 2,
                    "ppn": 22,
                }
            )
        case SatpMode.SV39 | SatpMode.SV48 | SatpMode.SV57:
            return StructLayout(
                {
                    "V": 1,
                    "R": 1,
                    "W": 1,
                    "X": 1,
                    "U": 1,
                    "G": 1,
                    "A": 1,
                    "D": 1,
                    "RSW": 2,
                    "ppn": 44,
                    "reserved": 7,
                    "PBMT": 2,
                    "N": 1,
                }
            )
        case _:
            raise ValueError(f"Unsupported SATP mode: {mode}")


def bits_per_level(mode: SatpMode) -> int:
    """Number of virtual address bits translated at each page table level."""
    num_entries = PAGE_SIZE // page_table_entry_format(mode).as_shape().width
    return num_entries.bit_length() - 1


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

    def elaborate(self, platform):
        m = TModule()
        m.submodules.resp_fwd = resp_fwd = Forwarder(self.layouts.accept)
        csr = DependencyContext.get().get_dependency(CSRInstancesKey())

        @def_method(m, self.request)
        def _(addr: Value):
            access_fault = Signal()
            page_fault = Signal()
            effective_priv_mode = Signal(PrivilegeLevel)

            priv_mode = csr.m_mode.priv_mode.read(m).data

            match self.mode:
                case AddressTranslatorMode.LSU:
                    mprv = csr.m_mode.mstatus_mprv.read(m).data
                    mpp = csr.m_mode.mstatus_mpp.read(m).data

                    m.d.av_comb += effective_priv_mode.eq(
                        (Mux(mprv & (priv_mode == PrivilegeLevel.MACHINE), mpp, priv_mode))
                    )

                case AddressTranslatorMode.INSTRUCTION:
                    m.d.av_comb += effective_priv_mode.eq(priv_mode)

            effective_satp_mode = Signal(SatpMode, init=SatpMode.BARE)

            if self.gen_params.supervisor_mode:
                with m.If(effective_priv_mode < PrivilegeLevel.MACHINE):
                    m.d.av_comb += effective_satp_mode.eq(csr.s_mode.satp_mode)

            poffset = Signal(PAGE_SIZE_LOG)
            ppn = Signal(self.gen_params.phys_addr_bits - PAGE_SIZE_LOG)
            vpn = Signal(self.gen_params.isa.xlen - PAGE_SIZE_LOG)

            m.d.av_comb += Cat(poffset, vpn).eq(addr)

            max_ppn = 1 << (self.gen_params.phys_addr_bits - PAGE_SIZE_LOG) - 1

            vpn_invalid = Signal()
            with m.Switch(effective_satp_mode):
                for mode in self.gen_params.vmem_params.supported_schemes - {SatpMode.BARE}:
                    vpn_len = bits_per_level(mode) * level_count(mode)

                    with m.Case(mode):
                        # virtual modes require sign-extended vaddr
                        m.d.av_comb += vpn_invalid.eq(vpn[vpn_len:].any() & ~vpn[vpn_len:].all())

            ppn_invalid = Signal()
            with m.Switch(effective_satp_mode):
                with m.Case(SatpMode.BARE):
                    m.d.av_comb += ppn.eq(vpn)
                    m.d.av_comb += ppn_invalid.eq(vpn > max_ppn)

                # TODO: implement actual page table walking

            with m.If(vpn_invalid):
                m.d.av_comb += page_fault.eq(1)

            with m.If(ppn_invalid):
                m.d.av_comb += access_fault.eq(1)

            resp_fwd.write(
                m,
                addr=addr,
                paddr=Cat(poffset, ppn),
                page_fault=page_fault,
                access_fault=access_fault,
            )

        @def_method(m, self.accept)
        def _():
            return resp_fwd.read(m)

        return m
