from amaranth import *
from amaranth.lib.data import StructLayout, ArrayLayout

from transactron import Method, TModule, def_method, Priority, Transaction
from transactron.utils import DependencyContext, mod_incr
from transactron.lib import Forwarder, condition, HwCounter

from coreblocks.arch.isa_consts import PAGE_SIZE_LOG, SatpMode
from coreblocks.interface.layouts import AddressTranslationLayouts
from coreblocks.interface.keys import SFenceVMAKey, CSRInstancesKey
from coreblocks.params import GenParams

from coreblocks.priv.vmem.iface import TLBBackingDevice

__all__ = [
    "FullyAssociativeTLB",
]


class TLBEntry(StructLayout):
    valid: Value
    asid: Value
    vpn: Value
    ppn: Value
    size_class: Value
    permissions: Value

    def __init__(self, gen_params: GenParams):
        super().__init__(
            {
                "valid": 1,
                "asid": gen_params.vmem_params.asidlen,
                "size_class": gen_params.vmem_params.tlb_size_class_bits,
                "vpn": gen_params.vmem_params.max_tlb_vpn_bits,
                "ppn": gen_params.phys_addr_bits - PAGE_SIZE_LOG,
                "permissions": gen_params.get(AddressTranslationLayouts).permissions,
            }
        )


class TLBCAM(Elaboratable):
    """A single set of a TLB CAM, containing multiple ways."""

    def __init__(self, gen_params: GenParams, ways: int):
        self.gen_params = gen_params
        self.ways = ways
        self.layout = gen_params.get(AddressTranslationLayouts)

        self.ways_data = Signal(ArrayLayout(TLBEntry(gen_params), ways))
        self.checked_asid = Signal(gen_params.vmem_params.asidlen)
        self.checked_vpn = Signal(gen_params.vmem_params.max_tlb_vpn_bits)
        self.replacement_data = Signal(range(ways))

        self.addr_match = Signal(ways)
        self.asid_match = Signal(ways)
        self.valid_match = Signal(ways)
        self.global_match = Signal(ways)

        self.full_match = Signal(ways)

        self.replace_candidate = Signal(range(ways))
        self.next_replacement_data = Signal.like(self.replacement_data)

    def elaborate(self, platform):
        m = TModule()

        for way in range(self.ways):
            m.d.comb += self.valid_match[way].eq(self.ways_data[way].valid)
            m.d.comb += self.global_match[way].eq(self.ways_data[way].permissions.g)
            m.d.comb += self.asid_match[way].eq(
                ~self.global_match[way] & (self.ways_data[way].asid == self.checked_asid)
            )

            # Address matches if the specified suffix on VPN matches based on size class
            bits_per_level = SatpMode.bits_per_page_table_level(self.gen_params.isa.xlen)
            with m.Switch(self.ways_data[way].size_class):
                for sz_class in range(self.gen_params.vmem_params.max_tlb_size_class + 1):
                    with m.Case(sz_class):
                        match_bits = bits_per_level * sz_class
                        m.d.comb += self.addr_match[way].eq(
                            self.checked_vpn[match_bits:] == self.ways_data[way].vpn[match_bits:]
                        )

        m.d.comb += self.full_match.eq(self.valid_match & self.addr_match & (self.asid_match | self.global_match))

        # Replacement candidate is the first invalid entry, or the round-robin entry if all are valid
        # The order of checks: currently present entry -> invalid entry -> round-robin.
        m.d.comb += self.replace_candidate.eq(self.replacement_data)

        for way in range(self.ways):
            with m.If(~self.valid_match[way]):
                m.d.comb += self.replace_candidate.eq(way)

        for way in range(self.ways):
            with m.If(self.full_match[way]):
                m.d.comb += self.replace_candidate.eq(way)

        m.d.comb += self.next_replacement_data.eq(mod_incr(self.replacement_data, self.ways))

        return m


class FullyAssociativeTLB(TLBBackingDevice, Elaboratable):
    """Fully associative TLB capable of same-cycle operations.
    Meant for L1 TLBs.
    """

    def __init__(
        self,
        gen_params: GenParams,
        *,
        entries: int,
        backing_resolver: TLBBackingDevice,
        perf_name_prefix: str = "mmu.tlb",
    ):
        if entries <= 0:
            raise ValueError("entries must be positive")

        self.gen_params = gen_params
        self.entries = entries
        self.backing_resolver = backing_resolver
        self.layout = gen_params.get(AddressTranslationLayouts)
        self.perf_name_prefix = perf_name_prefix

        self.request = Method(i=self.layout.tlb_request)
        self.accept = Method(o=self.layout.tlb_accept)

        self.sfence_vma = Method(i=self.layout.sfence_vma)
        self.dm = DependencyContext.get()
        self.dm.add_dependency(SFenceVMAKey(), self.sfence_vma)

        self.perf_loads = HwCounter(f"{self.perf_name_prefix}.loads", "Number of requests to the TLB")
        self.perf_hits = HwCounter(f"{self.perf_name_prefix}.hits")
        self.perf_misses = HwCounter(f"{self.perf_name_prefix}.misses")
        self.perf_flushes = HwCounter(f"{self.perf_name_prefix}.flushes")

    def elaborate(self, platform):
        m = TModule()

        m.submodules += [
            self.perf_loads,
            self.perf_hits,
            self.perf_misses,
            self.perf_flushes,
        ]

        csr = self.dm.get_dependency(CSRInstancesKey())

        vpn_bits = self.gen_params.vmem_params.max_tlb_vpn_bits
        asid_bits = self.gen_params.vmem_params.asidlen

        current_asid = Signal(asid_bits)
        m.d.comb += current_asid.eq(csr.s_mode.satp_asid)

        entries = Signal(ArrayLayout(TLBEntry(self.gen_params), self.entries))

        m.submodules.cam = cam = TLBCAM(self.gen_params, self.entries)
        m.d.comb += cam.ways_data.eq(entries)

        m.submodules.fwd = fwd = Forwarder(self.layout.tlb_accept)

        request_in_flight = Signal()
        requested_vpn = Signal(vpn_bits)

        with m.If(self.sfence_vma.run):
            m.d.comb += cam.checked_asid.eq(self.sfence_vma.data_in.asid)
            m.d.comb += cam.checked_vpn.eq(self.sfence_vma.data_in.vaddr >> PAGE_SIZE_LOG)
        with m.Elif(request_in_flight):
            m.d.comb += cam.checked_asid.eq(current_asid)
            m.d.comb += cam.checked_vpn.eq(requested_vpn)
        with m.Else():
            m.d.comb += cam.checked_asid.eq(current_asid)
            m.d.comb += cam.checked_vpn.eq(self.request.data_in.vpn)

        @def_method(m, self.request, ready=~request_in_flight)
        def _(vpn, write_aspect):
            self.perf_loads.incr(m)

            found_entry = Signal(TLBEntry(self.gen_params))

            for way in range(self.entries):
                with m.If(cam.full_match[way]):
                    m.d.av_comb += found_entry.eq(cam.ways_data[way])

            ask_backing = Signal()
            with m.If(~cam.full_match.any()):
                m.d.av_comb += ask_backing.eq(1)
            with m.Elif(write_aspect & ~found_entry.permissions.d):
                # We have found an entry, but it doesn't have the dirty bit set
                # NOTE: currently we would never actually need to ask the backing device,
                #   as we only implement Svade, so if this happens, we are almost sure
                #   the re-walk will not fix the issue.
                m.d.av_comb += ask_backing.eq(1)

            with condition(m) as branch:
                with branch(ask_backing):
                    self.perf_misses.incr(m)
                    m.d.sync += request_in_flight.eq(1)
                    m.d.sync += requested_vpn.eq(vpn)
                    self.backing_resolver.request(m, vpn=vpn, write_aspect=write_aspect)
                with branch():
                    self.perf_hits.incr(m)
                    fwd.write(
                        m,
                        result=AddressTranslationLayouts.TLBResult.HIT,
                        permissions=found_entry.permissions,
                        ppn=found_entry.ppn,
                        size_class=found_entry.size_class,
                    )

        # Slow path - refill from backing resolver
        with Transaction().body(m, ready=request_in_flight):
            resp = self.backing_resolver.accept(m)
            m.d.sync += request_in_flight.eq(0)

            fwd.write(m, resp)

            with m.If(resp.result == AddressTranslationLayouts.TLBResult.HIT):
                new_entry = Signal(TLBEntry(self.gen_params))
                m.d.av_comb += [
                    new_entry.valid.eq(1),
                    new_entry.asid.eq(current_asid),
                    new_entry.vpn.eq(requested_vpn),
                    new_entry.ppn.eq(resp.ppn),
                    new_entry.size_class.eq(resp.size_class),
                    new_entry.permissions.eq(resp.permissions),
                ]
                m.d.sync += cam.replacement_data.eq(cam.next_replacement_data)
                m.d.sync += entries[cam.replace_candidate].eq(new_entry)

        self.accept.provide(fwd.read)

        @def_method(m, self.sfence_vma, ready=~request_in_flight)
        def _(vaddr, asid, all_vaddrs, all_asids):
            self.perf_flushes.incr(m)

            for way in range(self.entries):
                with m.If((all_asids | cam.asid_match[way]) & (all_vaddrs | cam.addr_match[way])):
                    m.d.sync += entries[way].valid.eq(0)

        self.sfence_vma.add_conflict(self.request, Priority.LEFT)

        return m
