from amaranth import *
from amaranth.lib.data import StructLayout, View

from coreblocks.arch.isa_consts import SatpMode
from coreblocks.params.genparams import GenParams
from coreblocks.interface.layouts import AddressTranslationLayouts
from coreblocks.interface.keys import SFenceVMAKey

from transactron import *
from transactron.utils import DependencyContext

from coreblocks.priv.vmem.iface import TLBBackingDevice


class PTELayout(StructLayout):
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
        return PTEView(value, self)


class PTEView(View):
    def __init__(self, value, layout):
        self.xlen = layout.xlen
        super().__init__(value, layout)

    def permissions(self):
        return {
            "r": self.R,
            "w": self.W,
            "x": self.X,
            "u": self.U,
            "d": self.D,
        }

    def non_leaf(self):
        return ~self.R | ~self.W | ~self.X

    def bad_encoding(self):
        """Whether page-fault should be raised due to invalid PTE encoding."""
        is_bad = 0

        # W needs R
        is_bad |= self.W & ~self.R

        # RSW is reserved for software - ignored

        if self.gen_params.isa.xlen == 64:
            # Reserved bits must be zero
            is_bad |= self.reserved.any()
            is_bad |= self.PBMT.any()
            is_bad |= self.N

        return is_bad


class PageTableWalker(TLBBackingDevice, Elaboratable):
    """Hardware page table walker for virtual address translation."""

    def __init__(self, gen_params: GenParams) -> None:
        self.gen_params = gen_params
        self.layout = AddressTranslationLayouts(gen_params)
        self.request = Method(i=self.layout.tlb_request)
        self.accept = Method(o=self.layout.tlb_accept)

        self.sfence_vma = Method(i=self.layout.sfence_vma)
        self.dm = DependencyContext.get()
        self.dm.add_dependency(SFenceVMAKey(), self.sfence_vma)

    def elaborate(self, platform):
        m = TModule()

        @def_method(m, self.request)
        def _(arg):
            pass

        @def_method(m, self.accept)
        def _(arg):
            pass

        @def_method(m, self.sfence_vma)
        def _(arg):
            pass

        return m
