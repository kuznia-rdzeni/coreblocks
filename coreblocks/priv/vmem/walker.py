"""Page Table Walker - Hardware implementation of RISC-V page table walking."""

from amaranth import *
from amaranth.lib.data import StructLayout, View
from amaranth.utils import exact_log2

from coreblocks.arch.isa_consts import PAGE_SIZE, SatpMode, PAGE_SIZE_LOG
from coreblocks.params.genparams import GenParams
from coreblocks.interface.layouts import AddressTranslationLayouts
from coreblocks.interface.keys import CSRInstancesKey
from coreblocks.peripherals.bus_adapter import BusMasterInterface
from coreblocks.priv.pmp import PMPChecker, PMPOperationMode

from transactron import *
from transactron.utils import DependencyContext, HardwareLogger

from coreblocks.priv.vmem.iface import TLBBackingDevice


__all__ = ["PageTableWalker"]


log = HardwareLogger("mmu.walker")


class PTELayout(StructLayout):
    """Page Table Entry layout for RISC-V."""

    def __init__(self, gen_params: GenParams):
        # We assume all supported modes have the same PTE format.
        if not gen_params.vmem_params.supported_non_bare_schemes:
            raise ValueError("PTE layout cannot be determined without supported virtual memory schemes")

        assert SatpMode.SV64 not in gen_params.vmem_params.supported_schemes, "SV64 is not supported"

        self.gen_params = gen_params

        # there is only one vmem scheme for RV32, and all RV64 schemes share the same PTE format
        if self.gen_params.isa.xlen == 32:
            layout = {
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
        else:
            layout = {
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

        super().__init__(layout)

    def __call__(self, value):
        return PTEView(self, value)


class PTEView(View):
    """View of a Page Table Entry with helper methods."""

    def __init__(self, layout, value):
        self.gen_params: GenParams = layout.gen_params
        super().__init__(layout, value)

    def is_leaf(self):
        return self.R | self.X

    def invalid(self):
        is_bad = ~self.V

        # W needs R
        is_bad |= self.W & ~self.R

        # RSW is reserved for software - ignored

        if self.gen_params.isa.xlen == 64:
            # Reserved bits must be zero
            is_bad |= self.reserved.any()
            is_bad |= self.PBMT.any()
            is_bad |= self.N

        # Non-leaf PTEs have A and D bits reserved
        is_bad |= ~self.is_leaf() & (self.A | self.D)

        return is_bad


class PageTableWalker(TLBBackingDevice, Elaboratable):
    """Hardware page table walker for RISC-V virtual memory translation.

    This module implements a page table walker that translates virtual page numbers (VPN)
    to physical page numbers (PPN) by walking through the page table hierarchy according
    to the current SATP configuration.

    Supported virtual memory modes:
    - BARE: No translation (immediate page fault)
    - SV32: 32-bit virtual addresses, 2-level page table
    - SV39: 64-bit virtual addresses, 3-level page table
    - SV48: 64-bit virtual addresses, 4-level page table
    - SV57: 64-bit virtual addresses, 5-level page table

    Implements Svade semantics (exception on missing A/D bits).
    """

    def __init__(self, gen_params: GenParams, bus: BusMasterInterface) -> None:
        self.gen_params = gen_params
        self.layout = gen_params.get(AddressTranslationLayouts)
        self.request = Method(i=self.layout.tlb_request)
        self.accept = Method(o=self.layout.tlb_accept)
        self.dm = DependencyContext.get()
        self.bus = bus

    def elaborate(self, platform):
        m = TModule()

        csr = self.dm.get_dependency(CSRInstancesKey())
        m.submodules.pmp_checker = pmp_checker = PMPChecker(self.gen_params, mode=PMPOperationMode.MMU)

        pte_layout = PTELayout(self.gen_params)
        xlen = self.gen_params.isa.xlen
        bits_per_level = SatpMode.bits_per_page_table_level(xlen)
        pte_bytes = pte_layout.as_shape().width // 8

        assert (pte_bytes << bits_per_level) == PAGE_SIZE
        assert pte_layout.as_shape().width == self.gen_params.isa.xlen
        offset_bits = exact_log2(pte_bytes)

        max_levels = max(SatpMode.level_count(mode) for mode in self.gen_params.vmem_params.supported_non_bare_schemes)

        walk_level = Signal(range(max_levels))
        walk_vpn = Signal(self.gen_params.vmem_params.max_tlb_vpn_bits)
        is_store = Signal()
        pte_addr = Signal(self.gen_params.phys_addr_bits)
        ppn = Signal(self.gen_params.phys_addr_bits - PAGE_SIZE_LOG)
        access_fault = Signal()
        page_fault = Signal()

        accessed = Signal()
        permissions = Signal(self.layout.permissions)

        vpn_index = Signal(bits_per_level)
        m.d.comb += [
            vpn_index.eq(walk_vpn.word_select(walk_level, bits_per_level)),
            pte_addr.eq(Cat(C(0, offset_bits), vpn_index, ppn)),
            pmp_checker.paddr.eq(value=pte_addr),
        ]

        with m.FSM() as fsm:
            with m.State("IDLE"):
                with m.If(self.request.run):
                    m.next = "ISSUE"
            with m.State("DONE"):
                with m.If(self.accept.run):
                    m.next = "IDLE"
            with m.State("ISSUE"):
                with Transaction().body(m):
                    with m.If(~pmp_checker.result.r):
                        m.d.sync += access_fault.eq(1)
                        m.next = "DONE"
                    with m.Else():
                        self.bus.request_read(m, addr=(pte_addr >> offset_bits), sel=~0)
                        m.next = "EVAL"
            with m.State("EVAL"):
                with Transaction().body(m):
                    fetched = self.bus.get_read_response(m)
                    pte = Signal(pte_layout)
                    m.d.av_comb += pte.eq(fetched.data)

                    m.d.sync += [
                        permissions.r.eq(pte.R),
                        permissions.w.eq(pte.W),
                        permissions.x.eq(pte.X),
                        permissions.u.eq(pte.U),
                        permissions.d.eq(pte.D),
                        permissions.g.eq(pte.G),
                        accessed.eq(pte.A),
                    ]

                    m.d.sync += ppn.eq(pte.ppn)

                    max_ppn = (1 << (self.gen_params.phys_addr_bits - PAGE_SIZE_LOG)) - 1
                    with m.If(fetched.err):
                        m.d.sync += access_fault.eq(1)
                        m.next = "DONE"
                    with m.Elif(pte.invalid()):
                        m.d.sync += page_fault.eq(1)
                        m.next = "DONE"
                    with m.Elif(pte.ppn > max_ppn):
                        m.d.sync += access_fault.eq(1)
                        m.next = "DONE"
                    with m.Elif(pte.is_leaf()):
                        m.next = "DONE"
                    with m.Elif(walk_level == 0):
                        m.d.sync += page_fault.eq(1)
                        m.next = "DONE"
                    with m.Else():
                        m.d.sync += walk_level.eq(walk_level - 1)
                        m.next = "ISSUE"

        @def_method(m, self.request, ready=fsm.ongoing("IDLE"))
        def _(arg):
            m.d.sync += [
                walk_vpn.eq(arg.vpn),
                is_store.eq(arg.is_store),
                access_fault.eq(0),
                page_fault.eq(0),
            ]

            with m.Switch(csr.s_mode.satp_mode):
                for mode in self.gen_params.vmem_params.supported_non_bare_schemes:
                    with m.Case(mode):
                        m.d.sync += walk_level.eq(SatpMode.level_count(mode) - 1)
                with m.Default():
                    log.error(m, 1, "Unsupported SATP mode in page table walker")
                    m.d.sync += walk_level.eq(0)

            m.d.sync += ppn.eq(csr.s_mode.satp_ppn)

        @def_method(m, self.accept, ready=fsm.ongoing("DONE"))
        def _():
            result = Signal(AddressTranslationLayouts.TLBResult, init=AddressTranslationLayouts.TLBResult.HIT)

            ppn_misaligned = Signal()
            with m.Switch(walk_level):
                for level in range(max_levels):
                    with m.Case(level):
                        level_vpn_bits = bits_per_level * level
                        m.d.comb += ppn_misaligned.eq(ppn[:level_vpn_bits].any())

            with m.If(access_fault):
                m.d.av_comb += result.eq(AddressTranslationLayouts.TLBResult.ACCESS_FAULT)
            with m.Elif(page_fault | ppn_misaligned):
                m.d.av_comb += result.eq(AddressTranslationLayouts.TLBResult.PAGE_FAULT)
            with m.Elif(~accessed | (is_store & ~permissions.d)):
                # Svade semantics: if A/D bits are not properly set, treat it as a page fault
                m.d.av_comb += result.eq(AddressTranslationLayouts.TLBResult.PAGE_FAULT)
                # TODO: implement non Svade once LSU gets real atomic support
                #  -> just a CAS on last PTE with A/D bits set, and if it fails, restart the walk
            with m.Else():
                m.d.av_comb += result.eq(AddressTranslationLayouts.TLBResult.HIT)

            return {
                "result": result,
                "ppn": ppn,
                "permissions": permissions,
                "size_class": walk_level,
            }

        return m
