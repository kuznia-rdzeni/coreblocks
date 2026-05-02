"""Generic set-associative TLB with a backing page resolver."""

from __future__ import annotations

from amaranth import *
from amaranth.lib.data import StructLayout

from transactron import Method, TModule, def_method
from transactron.utils import DependencyContext

from coreblocks.arch.isa_consts import PAGE_SIZE_LOG
from coreblocks.interface.layouts import AddressTranslationLayouts
from coreblocks.interface.keys import SFenceVMAKey
from coreblocks.params import GenParams

from coreblocks.priv.vmem.iface import TLBBackingDevice

__all__ = [
    "TLBEntry",
    "TLB",
]


class TLBEntry(StructLayout):
    def __init__(self, gen_params: GenParams):
        vpn_width = gen_params.vmem_params.max_tlb_vpn_bits
        ppn_width = gen_params.phys_addr_bits - PAGE_SIZE_LOG
        asid_width = max(1, gen_params.vmem_params.asidlen)

        super().__init__(
            {
                "valid": 1,
                "global_mapping": 1,
                "asid": asid_width,
                "size_class": gen_params.vmem_params.tlb_size_class_bits,
                "vpn": vpn_width,
                "ppn": ppn_width,
                "r": 1,
                "w": 1,
                "x": 1,
                "u": 1,
                "d": 1,
            }
        )


class TLB(TLBBackingDevice, Elaboratable):
    def __init__(
        self,
        gen_params: GenParams,
        *,
        entries: int,
        ways: int,
        backing_resolver: TLBBackingDevice,
    ) -> None:
        if entries <= 0:
            raise ValueError("entries must be positive")
        if ways <= 0:
            raise ValueError("ways must be positive")
        if entries % ways != 0:
            raise ValueError("entries must be divisible by ways")

        self.gen_params = gen_params
        self.entries = entries
        self.ways = ways
        self.sets = entries // ways
        self.backing_resolver = backing_resolver
        self.entry_layout = TLBEntry(gen_params)
        self.layout = gen_params.get(AddressTranslationLayouts)

        self.request = Method(i=self.layout.tlb_request)
        self.accept = Method(o=self.layout.tlb_accept)

        self.sfence_vma = Method(i=self.layout.sfence_vma)
        self.dm = DependencyContext.get()
        self.dm.add_dependency(SFenceVMAKey(), self.sfence_vma)

    def elaborate(self, platform):
        m = TModule()

        m.submodules.backing_resolver = self.backing_resolver

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
