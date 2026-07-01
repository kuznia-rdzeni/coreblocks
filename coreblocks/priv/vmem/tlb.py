from dataclasses import dataclass

from amaranth import *
from amaranth.lib.data import StructLayout, ArrayLayout, View
import amaranth.lib.memory as memory

from transactron import Method, Methods, TModule, def_method, Priority, Transaction
from transactron.utils import DependencyContext, assign, mod_incr, OneHotMux
from transactron.lib import (
    BasicFifo,
    Forwarder,
    Pipe,
    HwCounter,
    FIFOLatencyMeasurer,
    Serializer,
    condition,
)

from coreblocks.arch.isa_consts import PAGE_SIZE_LOG, SatpMode
from coreblocks.interface.layouts import AddressTranslationLayouts
from coreblocks.interface.keys import SFenceVMABusyKey, SFenceVMAKey, CSRInstancesKey
from coreblocks.params import GenParams

from coreblocks.priv.vmem.iface import TLBBackingDevice

__all__ = [
    "FullyAssociativeTLB",
    "SetAssociativeTLB",
]


class TLBEntry(StructLayout):
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
    """A single set of a TLB CAM, containing multiple ways.

    Finds entries matching the VPN (taking into account size class) and ASID and returns bit-vectors of matches.
    """

    ways_data: View
    """Data for all ways, used for matching and replacement."""

    checked_asid: Signal
    """ASID to check for matches."""

    checked_vpn: Signal
    """VPN to check for matches."""

    valid_match: Signal
    """Bit-vector of valid entries."""

    addr_match: Signal
    """Bit-vector of ways matching the address (taking into account size class)."""

    asid_match: Signal
    """Bit-vector of ways matching the ASID (only non-global entries)."""

    global_match: Signal
    """Bit-vector of global entries."""

    full_match: Signal
    """Bit-vector of ways matching inputs - valid and address and (ASID or global)."""

    replacement_rr_index: Signal
    """Round-robin index for replacement."""

    replace_candidate: Signal
    """Index of the way to replace on a miss."""

    next_replacement_rr_index: Signal
    """Value of replacement_rr_index after replacement."""

    def __init__(self, gen_params: GenParams, ways: int, ports: int = 1):
        self.gen_params = gen_params
        self.ways = ways
        self.layout = gen_params.get(AddressTranslationLayouts)

        self.ways_data = Signal(ArrayLayout(TLBEntry(gen_params), ways))
        self.checked_asid = Signal(gen_params.vmem_params.asidlen)
        self.checked_vpn = Signal(gen_params.vmem_params.max_tlb_vpn_bits)
        self.replacement_rr_index = Signal(range(ways))

        self.addr_match = Signal(ways)
        self.asid_match = Signal(ways)
        self.valid_match = Signal(ways)
        self.global_match = Signal(ways)

        self.full_match = Signal(ways)

        self.replace_candidate = Signal(range(ways))
        self.next_replacement_rr_index = Signal.like(self.replacement_rr_index)

        self.matched_entry = Signal(TLBEntry(gen_params))

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
        m.d.comb += self.replace_candidate.eq(self.replacement_rr_index)

        for way in range(self.ways):
            with m.If(~self.valid_match[way]):
                m.d.comb += self.replace_candidate.eq(way)

        for way in range(self.ways):
            with m.If(self.full_match[way]):
                m.d.comb += self.replace_candidate.eq(way)

        m.d.comb += self.next_replacement_rr_index.eq(mod_incr(self.replacement_rr_index, self.ways))

        m.d.comb += self.matched_entry.eq(
            OneHotMux.create(
                m, [(self.full_match[way], self.ways_data[way]) for way in range(self.ways)], priority=True
            )
        )

        return m


class FullyAssociativeTLB(Elaboratable):
    """Fully associative TLB capable of same-cycle operations.
    Meant for L1 TLBs.
    """

    def __init__(
        self,
        gen_params: GenParams,
        *,
        entries: int,
        ports: int,
        backing_resolver: TLBBackingDevice,
        perf_name_prefix: str = "mmu.tlb",
    ):
        if entries <= 0:
            raise ValueError("entries must be positive")

        if ports <= 0:
            raise ValueError("the number of ports of TLB must be positive")

        self.gen_params = gen_params
        self.entries = entries
        self.ports = ports
        self.backing_resolver = backing_resolver
        self.layout = gen_params.get(AddressTranslationLayouts)
        self.perf_name_prefix = perf_name_prefix

        self.request = Methods(ports, i=self.layout.tlb_request)
        self.accept = Methods(ports, o=self.layout.tlb_accept)

        self.sfence_vma = Method(i=self.layout.sfence_vma)
        self.dm = DependencyContext.get()
        self.dm.add_dependency(SFenceVMAKey(), self.sfence_vma)

        self.sfence_busy = Signal()
        self.dm.add_dependency(SFenceVMABusyKey(), self.sfence_busy)

        self.perf_loads = HwCounter(f"{self.perf_name_prefix}.loads", "Number of requests to the TLB", ways=self.ports)
        self.perf_hits = HwCounter(f"{self.perf_name_prefix}.hits", ways=self.ports)
        self.perf_misses = HwCounter(f"{self.perf_name_prefix}.misses", ways=self.ports)
        self.perf_flushes = HwCounter(f"{self.perf_name_prefix}.flushes", ways=self.ports)
        self.perf_latency = FIFOLatencyMeasurer(
            f"{self.perf_name_prefix}.latency", slots_number=2, max_latency=500, ways=self.ports
        )

        self.ports_allocated = 0

    def get_port(self) -> TLBBackingDevice:
        """Returns a TLBBackingDevice from a specific port."""
        if self.ports_allocated >= self.ports:
            raise ValueError(f"No available ports for TLB with {self.ports} ports")

        port = self.ports_allocated
        self.ports_allocated += 1

        @dataclass(frozen=True)
        class _Port(TLBBackingDevice):
            request: Method
            accept: Method

        return _Port(
            request=self.request[port],
            accept=self.accept[port],
        )

    def elaborate(self, platform):
        m = TModule()

        m.submodules += [
            self.perf_loads,
            self.perf_hits,
            self.perf_misses,
            self.perf_flushes,
            self.perf_latency,
        ]

        csr = self.dm.get_dependency(CSRInstancesKey())

        vpn_bits = self.gen_params.vmem_params.max_tlb_vpn_bits
        asid_bits = self.gen_params.vmem_params.asidlen

        current_asid = Signal(asid_bits)
        m.d.av_comb += current_asid.eq(csr.s_mode.satp_asid)

        entries = Signal(ArrayLayout(TLBEntry(self.gen_params), self.entries))

        m.submodules.refill_flush_cam = refill_flush_cam = TLBCAM(self.gen_params, self.entries)
        m.d.comb += refill_flush_cam.ways_data.eq(entries)

        m.submodules.flush_queue = flush_queue = BasicFifo(self.layout.sfence_vma, depth=2)
        self.sfence_vma.provide(flush_queue.write)

        m.submodules.refill_info = refill_info = BasicFifo([("vpn", vpn_bits)], depth=1)

        refill_ret = Signal(self.layout.tlb_accept)

        with m.If(refill_info.level != 0):

            with Transaction(name="AcceptRefill").body(m) as accept_refill:
                req_data = refill_info.read(m)
                m.d.av_comb += refill_flush_cam.checked_vpn.eq(req_data.vpn)
                m.d.av_comb += refill_flush_cam.checked_asid.eq(current_asid)

                resp = self.backing_resolver.accept(m)
                m.d.av_comb += refill_ret.eq(resp)

                with m.If(cond=resp.result == AddressTranslationLayouts.TLBResult.HIT):
                    m.d.sync += refill_flush_cam.replacement_rr_index.eq(refill_flush_cam.next_replacement_rr_index)
                    m.d.sync += assign(
                        entries[refill_flush_cam.replace_candidate],
                        {
                            "valid": 1,
                            "asid": current_asid,
                            "vpn": req_data.vpn,
                            "ppn": resp.ppn,
                            "size_class": resp.size_class,
                            "permissions": resp.permissions,
                        },
                    )

        with m.Else():

            with Transaction(name="Flush").body(m):
                self.perf_flushes.incr(m)

                req = flush_queue.read(m)
                m.d.av_comb += refill_flush_cam.checked_asid.eq(req.asid)
                m.d.av_comb += refill_flush_cam.checked_vpn.eq(req.vaddr >> PAGE_SIZE_LOG)

                for way in range(self.entries):
                    with m.If(
                        (req.all_asids | refill_flush_cam.asid_match[way])
                        & (req.all_vaddrs | refill_flush_cam.addr_match[way])
                    ):
                        m.d.sync += entries[way].valid.eq(0)

        def do_query(cam, is_store):
            ask_backing = Signal()
            with m.If(~cam.full_match.any()):
                m.d.av_comb += ask_backing.eq(1)
            if self.gen_params.vmem_params.supports_auto_a_d_management:
                with m.Elif(is_store & ~cam.matched_entry.permissions.d):
                    # We have found an entry, but it doesn't have the dirty bit set
                    # Ask the backing resolver to set it (Svade semantic)
                    m.d.av_comb += ask_backing.eq(1)

            ret = {
                "result": AddressTranslationLayouts.TLBResult.HIT,
                "permissions": cam.matched_entry.permissions,
                "ppn": cam.matched_entry.ppn,
                "size_class": cam.matched_entry.size_class,
            }

            return ask_backing, ret

        for port in range(self.ports):
            cam = TLBCAM(self.gen_params, self.entries)
            m.d.comb += cam.ways_data.eq(entries)

            result_fwd = Forwarder(self.layout.tlb_accept)
            m.submodules[f"result_fwd_{port}"] = result_fwd
            m.submodules[f"cam_{port}"] = cam

            slow_path = Signal()
            vpn_req = Signal(vpn_bits)
            is_store_req = Signal()

            with m.If(~slow_path):

                @def_method(m, self.request[port])
                def _(vpn, is_store):
                    self.perf_loads.incr(m)
                    self.perf_latency.start(m)

                    m.d.av_comb += cam.checked_vpn.eq(vpn)
                    m.d.av_comb += cam.checked_asid.eq(current_asid)
                    ask_backing, ret = do_query(cam, is_store)

                    with m.If(ask_backing):
                        self.perf_misses.incr[port](m)
                        m.d.sync += [
                            slow_path.eq(1),
                            vpn_req.eq(vpn),
                            is_store_req.eq(is_store),
                        ]
                    with m.Else():
                        self.perf_hits.incr[port](m)
                        result_fwd.write(m, ret)

            with m.Else():

                with Transaction(name=f"AsyncResolve_{port}").body(m) as t:
                    m.d.av_comb += cam.checked_vpn.eq(vpn_req)
                    m.d.av_comb += cam.checked_asid.eq(current_asid)

                    ask_backing, ret = do_query(cam, is_store_req)

                    with condition(m) as branch:
                        with branch(~ask_backing):
                            result_fwd.write(m, ret)
                            m.d.sync += slow_path.eq(0)
                        with branch((refill_info.head.vpn == vpn_req) & accept_refill.run):
                            # fast path - hit from current refill
                            result_fwd.write(m, refill_ret)
                            m.d.sync += slow_path.eq(0)
                        with branch(ask_backing & (flush_queue.level == 0)):
                            self.backing_resolver.request(m, vpn=vpn_req, is_store=is_store_req)
                            refill_info.write(m, vpn=vpn_req)

                accept_refill.schedule_before(t)

            @def_method(m, self.accept[port])
            def _():
                self.perf_latency.stop[port](m)
                return result_fwd.read(m)

        m.d.comb += self.sfence_busy.eq(flush_queue.level != 0)

        return m


class SetAssociativeTLB(Elaboratable):
    def __init__(
        self,
        gen_params: GenParams,
        *,
        entries: int,
        ways: int,
        ports: int,
        backing_resolver: TLBBackingDevice,
        perf_name_prefix: str = "mmu.tlb",
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
        self.ports = ports
        self.backing_resolver = backing_resolver
        self.layout = gen_params.get(AddressTranslationLayouts)
        self.perf_name_prefix = perf_name_prefix

        self.request = Methods(ports, i=self.layout.tlb_request)
        self.accept = Methods(ports, o=self.layout.tlb_accept)
        self.sfence_vma = Method(i=self.layout.sfence_vma)
        self.dm = DependencyContext.get()
        self.dm.add_dependency(SFenceVMAKey(), self.sfence_vma)

        self.perf_loads = HwCounter(f"{self.perf_name_prefix}.loads", "Number of requests to the TLB")
        self.perf_hits = HwCounter(f"{self.perf_name_prefix}.hits")
        self.perf_misses = HwCounter(f"{self.perf_name_prefix}.misses")
        self.perf_flushes = HwCounter(f"{self.perf_name_prefix}.flushes")
        self.perf_latency = FIFOLatencyMeasurer(f"{self.perf_name_prefix}.latency", slots_number=2, max_latency=500)

        self.ports_allocated = 0

    def get_port(self) -> TLBBackingDevice:
        """Returns a TLBBackingDevice from a specific port."""
        if self.ports_allocated >= self.ports:
            raise ValueError(f"No available ports for TLB with {self.ports} ports")

        port = self.ports_allocated
        self.ports_allocated += 1

        @dataclass(frozen=True)
        class _Port(TLBBackingDevice):
            request: Method
            accept: Method

        return _Port(
            request=self.request[port],
            accept=self.accept[port],
        )

    def elaborate(self, platform):
        m = TModule()

        m.submodules += [
            self.perf_loads,
            self.perf_hits,
            self.perf_misses,
            self.perf_flushes,
            self.perf_latency,
        ]

        csr = self.dm.get_dependency(CSRInstancesKey())

        vpn_bits = self.gen_params.vmem_params.max_tlb_vpn_bits
        asid_bits = self.gen_params.vmem_params.asidlen
        set_index_bits = (self.sets - 1).bit_length()

        current_asid = Signal(asid_bits)
        m.d.comb += current_asid.eq(csr.s_mode.satp_asid)

        m.submodules.cam = cam = TLBCAM(self.gen_params, self.ways)

        m.submodules.mem = mem = memory.Memory(
            shape=ArrayLayout(TLBEntry(self.gen_params), self.ways), depth=self.sets, init=[]
        )
        set_rd = mem.read_port()
        set_wr = mem.write_port()
        m.d.comb += cam.ways_data.eq(set_rd.data)

        m.submodules.rd_mem = rd_mem = memory.Memory(shape=cam.replacement_rr_index.shape(), depth=self.sets, init=[])
        rd_rd = rd_mem.read_port()
        rd_wr = rd_mem.write_port()
        m.d.comb += cam.replacement_rr_index.eq(rd_rd.data)

        m.submodules.fwd = fwd = Forwarder(self.layout.tlb_accept)

        flushing = Signal(init=1)
        refill_in_progress = Signal()

        m.submodules.request_pipe = request_pipe = Pipe(self.layout.tlb_request)

        requested_set = Signal(set_index_bits)
        requested_class = Signal(self.gen_params.vmem_params.tlb_size_class_bits)

        def vpn_to_set_idx(vpn, size_class):
            bits_per_level = SatpMode.bits_per_page_table_level(self.gen_params.isa.xlen)
            return vpn.word_select(size_class, bits_per_level)

        request = Method(i=self.layout.tlb_request)
        accept = Method(o=self.layout.tlb_accept)

        m.submodules.port_serializer = port_serializer = Serializer(
            port_count=self.ports,
            serialized_req_method=request,
            serialized_resp_method=accept,
        )

        for port in range(self.ports):
            self.request[port].provide(port_serializer.serialize_in[port])
            self.accept[port].provide(port_serializer.serialize_out[port])

        @def_method(m, request, ready=~flushing)
        def _(vpn, is_store):
            self.perf_loads.incr(m)
            self.perf_latency.start(m)

            set_idx = vpn_to_set_idx(vpn, 0)
            m.d.sync += requested_set.eq(set_idx)
            m.d.sync += requested_class.eq(0)

            m.d.comb += set_rd.addr.eq(set_idx)
            m.d.comb += set_rd.en.eq(1)

            m.d.sync += cam.checked_asid.eq(current_asid)
            m.d.sync += cam.checked_vpn.eq(vpn)

            request_pipe.write(m, vpn=vpn, is_store=is_store)

        with Transaction(name="TLBLookup").body(m, ready=~refill_in_progress):
            req = request_pipe.peek(m)

            miss = Signal()
            ask_backing = Signal()

            m.d.av_comb += miss.eq(~cam.full_match.any())

            if self.gen_params.vmem_params.supports_auto_a_d_management:
                if ~miss & req.is_store & ~cam.matched_entry.permissions.d:
                    m.d.av_comb += ask_backing.eq(1)

            max_class = self.gen_params.vmem_params.max_tlb_size_class
            with m.If(miss & (requested_class == max_class)):
                m.d.av_comb += ask_backing.eq(1)

            with m.If(ask_backing):
                self.perf_misses.incr(m)
                m.d.sync += refill_in_progress.eq(1)
                self.backing_resolver.request(m, vpn=req.vpn, is_store=req.is_store)
            with m.Elif(miss & (requested_class < max_class)):
                set_idx = vpn_to_set_idx(req.vpn, requested_class + 1)
                m.d.sync += requested_set.eq(set_idx)
                m.d.sync += requested_class.eq(requested_class + 1)

                m.d.comb += set_rd.addr.eq(set_idx)
                m.d.comb += set_rd.en.eq(1)
            with m.Else():
                request_pipe.read(m)
                self.perf_hits.incr(m)

                fwd.write(
                    m,
                    result=AddressTranslationLayouts.TLBResult.HIT,
                    permissions=cam.matched_entry.permissions,
                    ppn=cam.matched_entry.ppn,
                    size_class=cam.matched_entry.size_class,
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
                        request_pipe.read(m)
                        fwd.write(m, resp)
                        m.d.sync += refill_in_progress.eq(0)

            with m.State("REFILL"):
                with Transaction().body(m):
                    req = request_pipe.read(m)

                    fwd.write(m, refill_response)
                    m.d.sync += refill_in_progress.eq(0)

                    new_entry = Signal(TLBEntry(self.gen_params))
                    m.d.top_comb += [
                        new_entry.valid.eq(1),
                        new_entry.asid.eq(current_asid),
                        new_entry.vpn.eq(req.vpn),
                        new_entry.ppn.eq(refill_response.ppn),
                        new_entry.size_class.eq(refill_response.size_class),
                        new_entry.permissions.eq(refill_response.permissions),
                    ]

                    m.d.comb += rd_wr.data.eq(cam.next_replacement_rr_index)
                    m.d.comb += rd_wr.addr.eq(refill_set_idx)
                    m.d.comb += set_wr.addr.eq(refill_set_idx)
                    m.d.comb += set_wr.data.eq(set_rd.data)
                    m.d.comb += set_wr.data[cam.replace_candidate].eq(new_entry)

                    with m.If(refill_response.result == AddressTranslationLayouts.TLBResult.HIT):
                        m.d.comb += rd_wr.en.eq(1)
                        m.d.comb += set_wr.en.eq(1)

                    m.next = "IDLE"

        @def_method(m, accept)
        def _():
            self.perf_latency.stop(m)
            return fwd.read(m)

        # the flush after reset will start with garbage data in the CAM, but we do not care, as
        # it is a full flush and will invalidate all entries from the first set. Following set flushes
        # will have correct data
        flush_vpn = Signal(vpn_bits)
        flush_all_vaddrs = Signal(init=1)
        flush_all_asids = Signal(init=1)
        flush_set = Signal(set_index_bits)
        flush_size_class = Signal(self.gen_params.vmem_params.tlb_size_class_bits)
        flush_fetched = Signal()

        @def_method(m, self.sfence_vma, ready=~flushing & ~request_pipe.read.ready & ~refill_in_progress)
        def _(vaddr, asid, all_vaddrs, all_asids):
            self.perf_flushes.incr(m)

            m.d.sync += flushing.eq(1)
            m.d.sync += cam.checked_asid.eq(asid)
            m.d.sync += cam.checked_vpn.eq(vaddr >> PAGE_SIZE_LOG)
            m.d.sync += flush_vpn.eq(vaddr >> PAGE_SIZE_LOG)
            m.d.sync += flush_all_vaddrs.eq(all_vaddrs)
            m.d.sync += flush_all_asids.eq(all_asids)

            m.d.sync += flush_set.eq(Mux(all_vaddrs, 0, vpn_to_set_idx(vaddr >> PAGE_SIZE_LOG, 0)))
            m.d.sync += flush_fetched.eq(0)
            m.d.sync += flush_size_class.eq(0)

            m.d.comb += set_rd.addr.eq(flush_set)
            m.d.comb += set_rd.en.eq(1)

        self.sfence_vma.add_conflict(request, Priority.LEFT)

        with m.If(flushing):
            m.d.comb += set_wr.data.eq(set_rd.data)
            for way in range(self.ways):
                with m.If((flush_all_asids | cam.asid_match[way]) & (flush_all_vaddrs | cam.addr_match[way])):
                    m.d.comb += set_wr.data[way].valid.eq(0)

            m.d.comb += set_wr.addr.eq(flush_set)
            m.d.comb += set_wr.en.eq(1)

            next_flush_set = Signal(set_index_bits)
            flush_done = Signal()

            with m.If(flush_all_vaddrs):
                m.d.comb += next_flush_set.eq(flush_set + 1)
                m.d.comb += flush_done.eq(flush_set == self.sets - 1)
            with m.Else():
                m.d.comb += next_flush_set.eq(vpn_to_set_idx(flush_vpn, flush_size_class + 1))
                m.d.sync += flush_size_class.eq(flush_size_class + 1)

                with m.If(flush_size_class == self.gen_params.vmem_params.max_tlb_size_class):
                    m.d.comb += flush_done.eq(1)

            m.d.sync += flush_set.eq(next_flush_set)

            m.d.comb += set_rd.addr.eq(next_flush_set)
            m.d.comb += set_rd.en.eq(1)

            with m.If(flush_done):
                m.d.sync += flushing.eq(0)

        # SAFETY: As module fully blocks requests after getting a flush request, there is no need to
        # expose the `sfence_busy` signal, as all later requests are guaranteed to see the flush.

        return m
