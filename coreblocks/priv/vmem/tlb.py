from amaranth import *
from amaranth.lib.data import StructLayout, ArrayLayout
import amaranth.lib.memory as memory

from transactron import Method, TModule, def_method, Priority, Transaction
from transactron.utils import DependencyContext, mod_incr
from transactron.lib import Forwarder, Pipe

from coreblocks.arch.isa_consts import PAGE_SIZE_LOG, SatpMode
from coreblocks.interface.layouts import AddressTranslationLayouts
from coreblocks.interface.keys import SFenceVMAKey, CSRInstancesKey
from coreblocks.params import GenParams

from coreblocks.priv.vmem.iface import TLBBackingDevice

__all__ = [
    "FullyAssociativeTLB",
    "SetAssociativeTLB",
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
    ):
        if entries <= 0:
            raise ValueError("entries must be positive")

        self.gen_params = gen_params
        self.entries = entries
        self.backing_resolver = backing_resolver
        self.layout = gen_params.get(AddressTranslationLayouts)

        self.request = Method(i=self.layout.tlb_request)
        self.accept = Method(o=self.layout.tlb_accept)

        self.sfence_vma = Method(i=self.layout.sfence_vma)
        self.dm = DependencyContext.get()
        self.dm.add_dependency(SFenceVMAKey(), self.sfence_vma)

    def elaborate(self, platform):
        m = TModule()

        csr = self.dm.get_dependency(CSRInstancesKey())

        vpn_bits = self.gen_params.vmem_params.max_tlb_vpn_bits
        asid_bits = self.gen_params.vmem_params.asidlen

        current_asid = Signal(asid_bits)
        m.d.comb += current_asid.eq(csr.s_mode.satp_asid)

        entries = Signal(ArrayLayout(TLBEntry(self.gen_params), self.entries))

        m.submodules.cam = cam = TLBCAM(self.gen_params, self.entries)
        m.d.comb += cam.ways_data.eq(entries)

        m.submodules.fwd = fwd = Forwarder(self.layout.tlb_accept)
        m.submodules.slow_fwd = slow_fwd = Forwarder(self.layout.tlb_request)

        request_in_flight = Signal()
        requested_vpn = Signal(vpn_bits)

        @def_method(m, self.request, ready=~request_in_flight)
        def _(vpn, write_aspect):
            m.d.comb += cam.checked_asid.eq(current_asid)
            m.d.comb += cam.checked_vpn.eq(vpn)

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

            with m.If(ask_backing):
                m.d.sync += request_in_flight.eq(1)
                m.d.sync += requested_vpn.eq(vpn)
                slow_fwd.write(m, vpn=vpn, write_aspect=write_aspect)
            with m.Else():
                fwd.write(
                    m,
                    result=AddressTranslationLayouts.TLBResult.HIT,
                    permissions=found_entry.permissions,
                    ppn=found_entry.ppn,
                    size_class=found_entry.size_class,
                )

        with Transaction().body(m):
            req = slow_fwd.read(m)
            self.backing_resolver.request(m, vpn=req.vpn, write_aspect=req.write_aspect)

        # Slow path - refill from backing resolver
        with Transaction().body(m, ready=request_in_flight):
            resp = self.backing_resolver.accept(m)
            m.d.sync += request_in_flight.eq(0)

            m.d.comb += cam.checked_vpn.eq(requested_vpn)
            m.d.comb += cam.checked_asid.eq(current_asid)

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
            m.d.comb += cam.checked_asid.eq(asid)
            m.d.comb += cam.checked_vpn.eq(vaddr >> PAGE_SIZE_LOG)

            for way in range(self.entries):
                with m.If((all_asids | cam.asid_match[way]) & (all_vaddrs | cam.addr_match[way])):
                    m.d.sync += entries[way].valid.eq(0)

        self.sfence_vma.add_conflict(self.request, Priority.LEFT)

        return m


class SetAssociativeTLB(TLBBackingDevice, Elaboratable):
    def __init__(
        self,
        gen_params: GenParams,
        *,
        entries: int,
        ways: int,
        backing_resolver: TLBBackingDevice,
    ):
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
        self.layout = gen_params.get(AddressTranslationLayouts)

        self.request = Method(i=self.layout.tlb_request)
        self.accept = Method(o=self.layout.tlb_accept)
        self.sfence_vma = Method(i=self.layout.sfence_vma)
        self.dm = DependencyContext.get()
        self.dm.add_dependency(SFenceVMAKey(), self.sfence_vma)

    def elaborate(self, platform):
        m = TModule()

        csr = self.dm.get_dependency(CSRInstancesKey())

        vpn_bits = self.gen_params.vmem_params.max_tlb_vpn_bits
        asid_bits = self.gen_params.vmem_params.asidlen
        set_index_bits = (self.sets - 1).bit_length()

        current_asid = Signal(asid_bits)
        m.d.comb += current_asid.eq(csr.s_mode.satp_asid)

        # Single CAM instance that will be used to check each set
        m.submodules.cam = cam = TLBCAM(self.gen_params, self.ways)

        # All sets stored in synchronous memory
        # entries_array[set_index][way_index] = TLBEntry
        m.submodules.mem = mem = memory.Memory(
            shape=ArrayLayout(TLBEntry(self.gen_params), self.ways), depth=self.sets, init=[]
        )
        set_rd = mem.read_port()
        set_wr = mem.write_port()
        m.d.comb += cam.ways_data.eq(set_rd.data)

        # replacement data for each set
        m.submodules.rd_mem = rd_mem = memory.Memory(shape=cam.replacement_data.shape(), depth=self.sets, init=[])
        rd_rd = rd_mem.read_port()
        rd_wr = rd_mem.write_port()
        m.d.comb += cam.replacement_data.eq(rd_rd.data)

        m.submodules.fwd = fwd = Forwarder(self.layout.tlb_accept)

        flushing = Signal(init=1)

        m.submodules.request_pipe = request_pipe = Pipe(self.layout.tlb_request)

        requested_set = Signal(set_index_bits)
        requested_class = Signal(self.gen_params.vmem_params.tlb_size_class_bits)

        def vpn_to_set_idx(vpn, size_class):
            # The set index bits are taken from the VPN bits above the page offset, starting from
            # the bit corresponding to the size class
            bits_per_level = SatpMode.bits_per_page_table_level(self.gen_params.isa.xlen)
            return vpn.word_select(size_class, bits_per_level)

        @def_method(m, self.request, ready=~flushing)
        def _(vpn, write_aspect):
            set_idx = vpn_to_set_idx(vpn, 0)
            m.d.sync += requested_set.eq(set_idx)
            m.d.sync += requested_class.eq(0)

            m.d.comb += set_rd.addr.eq(set_idx)
            m.d.comb += set_rd.en.eq(1)

            m.d.sync += cam.checked_asid.eq(current_asid)
            m.d.sync += cam.checked_vpn.eq(vpn)

            request_pipe.write(m, vpn=vpn, write_aspect=write_aspect)

        slow_path = Signal()

        with Transaction(name="TLBLookup").body(m, ready=~slow_path):
            req = request_pipe.peek(m)

            valid_vec = Signal(self.ways)
            m.d.av_comb += valid_vec.eq(cam.valid_match & cam.addr_match & (cam.asid_match | cam.global_match))

            found_entry = Signal(TLBEntry(self.gen_params))

            for way in range(self.ways):
                with m.If(valid_vec[way]):
                    m.d.av_comb += found_entry.eq(cam.ways_data[way])

            miss = Signal()
            ask_backing = Signal()

            m.d.av_comb += miss.eq(~valid_vec.any())

            with m.If(~miss & req.write_aspect & ~found_entry.permissions.d):
                m.d.av_comb += ask_backing.eq(1)

            max_class = self.gen_params.vmem_params.max_tlb_size_class
            with m.If(miss & (requested_class == max_class)):
                m.d.av_comb += ask_backing.eq(1)

            with m.If(ask_backing):
                m.d.sync += slow_path.eq(1)
                self.backing_resolver.request(m, vpn=req.vpn, write_aspect=req.write_aspect)
            with m.Elif(miss & (requested_class < max_class)):
                # We have a miss, but the bigger page classes may still hit
                set_idx = vpn_to_set_idx(req.vpn, requested_class + 1)
                m.d.sync += requested_set.eq(set_idx)
                m.d.sync += requested_class.eq(requested_class + 1)

                m.d.comb += set_rd.addr.eq(set_idx)
                m.d.comb += set_rd.en.eq(1)
            with m.Else():
                # consume the request and return the hit result
                request_pipe.read(m)

                fwd.write(
                    m,
                    result=AddressTranslationLayouts.TLBResult.HIT,
                    permissions=found_entry.permissions,
                    ppn=found_entry.ppn,
                    size_class=found_entry.size_class,
                )

        refill_set_idx = Signal(set_index_bits)
        refill_response = Signal(self.layout.tlb_accept)

        with m.FSM():
            with m.State("IDLE"):
                with Transaction().body(m):
                    req = request_pipe.peek(m)
                    resp = self.backing_resolver.accept(m)

                    set_idx = vpn_to_set_idx(req.vpn, resp.size_class)
                    m.d.sync += refill_set_idx.eq(set_idx)
                    m.d.sync += refill_response.eq(resp)

                    m.d.comb += set_rd.addr.eq(set_idx)
                    m.d.comb += rd_rd.addr.eq(set_idx)
                    m.d.comb += set_rd.en.eq(1)
                    m.d.comb += rd_rd.en.eq(1)

                    with m.If(resp.result == AddressTranslationLayouts.TLBResult.HIT):
                        m.next = "REFILL"
                    with m.Else():
                        # Miss in the backing resolver - just forward the miss response
                        request_pipe.read(m)
                        fwd.write(m, resp)

            with m.State("REFILL"):
                with Transaction().body(m):
                    # We have received a valid PTE from the backing resolver and have the correct set index
                    req = request_pipe.read(m)

                    fwd.write(m, refill_response)
                    m.d.sync += slow_path.eq(0)

                    new_entry = Signal(TLBEntry(self.gen_params))
                    m.d.av_comb += [
                        new_entry.valid.eq(1),
                        new_entry.asid.eq(current_asid),
                        new_entry.vpn.eq(req.vpn),
                        new_entry.ppn.eq(refill_response.ppn),
                        new_entry.size_class.eq(refill_response.size_class),
                        new_entry.permissions.eq(refill_response.permissions),
                    ]

                    m.d.comb += rd_wr.data.eq(cam.next_replacement_data)
                    m.d.comb += rd_wr.addr.eq(refill_set_idx)
                    m.d.comb += rd_wr.en.eq(1)

                    m.d.comb += set_wr.data.eq(set_rd.data)
                    m.d.comb += set_wr.data[cam.replace_candidate].eq(new_entry)
                    m.d.comb += set_wr.addr.eq(refill_set_idx)
                    m.d.comb += set_wr.en.eq(1)

        @def_method(m, self.accept)
        def _():
            return fwd.read(m)

        flush_vpn = Signal(vpn_bits)
        flush_asid = Signal(asid_bits)
        flush_all_vaddrs = Signal(init=1)
        flush_all_asids = Signal(init=1)
        flush_set = Signal(set_index_bits)
        flush_size_class = Signal(self.gen_params.vmem_params.tlb_size_class_bits)
        flush_fetched = Signal()

        @def_method(m, self.sfence_vma, ready=~flushing)
        def _(vaddr, asid, all_vaddrs, all_asids):
            m.d.sync += flushing.eq(1)
            m.d.sync += flush_vpn.eq(vaddr >> PAGE_SIZE_LOG)
            m.d.sync += flush_asid.eq(asid)
            m.d.sync += flush_all_vaddrs.eq(all_vaddrs)
            m.d.sync += flush_all_asids.eq(all_asids)

            m.d.sync += flush_set.eq(Mux(flush_all_vaddrs, 0, vpn_to_set_idx(flush_vpn, 0)))
            m.d.sync += flush_fetched.eq(0)
            m.d.sync += flush_size_class.eq(0)

            # we block new inputs, wait for the current lookup to finish and then perform flush routine

        self.sfence_vma.add_conflict(self.request, Priority.LEFT)

        with Transaction(name="flush").body(m, ready=flushing & ~slow_path):
            with m.If(~flush_fetched):
                m.d.comb += set_rd.addr.eq(flush_set)
                m.d.comb += set_rd.en.eq(1)
                m.d.sync += cam.checked_asid.eq(flush_asid)
                m.d.sync += cam.checked_vpn.eq(flush_vpn)

                m.d.sync += flush_fetched.eq(1)
            with m.Else():
                # we have flush_set opened - invalidate the matching entries and move to the next set
                m.d.comb += set_wr.data.eq(set_rd.data)
                for way in range(self.ways):
                    with m.If((flush_all_asids | cam.asid_match[way]) & (flush_all_vaddrs | cam.addr_match[way])):
                        m.d.av_comb += set_wr.data[way].valid.eq(0)

                m.d.comb += set_wr.addr.eq(flush_set)
                m.d.comb += set_wr.en.eq(1)

                next_flush_set = Signal(set_index_bits)
                flush_done = Signal()

                with m.If(flush_all_vaddrs):
                    m.d.av_comb += next_flush_set.eq(flush_set + 1)
                    m.d.av_comb += flush_done.eq(flush_set == self.sets - 1)
                with m.Else():
                    with m.If(flush_size_class == self.gen_params.vmem_params.max_tlb_size_class):
                        m.d.av_comb += flush_done.eq(1)
                    with m.Else():
                        m.d.av_comb += next_flush_set.eq(vpn_to_set_idx(flush_vpn, flush_size_class + 1))
                        m.d.sync += flush_size_class.eq(flush_size_class + 1)

                m.d.sync += flush_set.eq(next_flush_set)

                m.d.comb += set_rd.addr.eq(next_flush_set)
                m.d.comb += set_rd.en.eq(1)

                with m.If(flush_done):
                    m.d.sync += flushing.eq(0)

        return m
