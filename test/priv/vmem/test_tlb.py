import random
from typing import Optional

from attr import dataclass

from amaranth import *

import pytest
from transactron import *
from transactron.lib import Adapter, AdapterTrans
from transactron.utils import DependencyContext, ModuleConnector
from transactron.testing import (
    ProcessContext,
    TestCaseWithSimulator,
    TestbenchContext,
    TestbenchIO,
    def_method_mock,
    SimpleTestCircuit,
    MethodMock,
    CallTrigger,
)

from coreblocks.arch.isa_consts import PAGE_SIZE_LOG, SatpMode
from coreblocks.interface.keys import CSRInstancesKey, SFenceVMAKey
from coreblocks.interface.layouts import AddressTranslationLayouts
from coreblocks.params import GenParams, configurations
from coreblocks.priv.csr.csr_instances import CSRInstances
from coreblocks.priv.vmem.iface import TLBBackingDevice
from coreblocks.priv.vmem.tlb import FullyAssociativeTLB


@dataclass(frozen=True)
class Permissions:
    r: int = 0
    w: int = 0
    x: int = 0
    u: int = 0
    d: int = 0


class MockTLBBackingDevice(TLBBackingDevice, Elaboratable):
    """Mock backing device for TLB testing."""

    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params
        self.csr_instances = DependencyContext.get().get_dependency(CSRInstancesKey())

        self.layout = gen_params.get(AddressTranslationLayouts)

        self.request_mock = TestbenchIO(Adapter(i=self.layout.tlb_request))
        self.accept_mock = TestbenchIO(Adapter(o=self.layout.tlb_accept))

        self.request = self.request_mock.adapter.iface
        self.accept = self.accept_mock.adapter.iface

        # Storage for mock translations: (vpn, asid) -> (ppn, permissions, size_class, result)
        self.translations = dict()

        self.ready = False
        self.translated = []

        self.asid = -1

    def size_class_mask(self, size_class: int):
        bits_per_size_class = self.gen_params.vmem_params.page_table_level_bits
        return -(1 << (bits_per_size_class * size_class))

    def add_translation(
        self,
        vpn: int,
        ppn: int,
        permissions: Permissions = Permissions(),
        size_class: int = 0,
        asid: Optional[int] = None,
    ):
        """Add a translation to the backing device.
        asid == None means global entry.
        """

        assert 0 <= size_class <= self.gen_params.vmem_params.max_tlb_size_class
        size_class_mask = self.size_class_mask(size_class)
        assert (ppn & ~size_class_mask) == 0, "PPN must be aligned to the size class"
        vpn = vpn & size_class_mask  # Align VPN to the size class
        assert permissions.r or not permissions.w

        self.translations[(vpn, asid)] = (
            ppn,
            permissions,
            size_class,
            AddressTranslationLayouts.TLBResult.HIT,
        )

    def add_access_fault(self, vpn: int, asid: Optional[int] = None):
        """Add an access fault for the given VPN and ASID."""
        self.translations[(vpn, asid)] = (
            0,
            Permissions(),
            0,
            AddressTranslationLayouts.TLBResult.ACCESS_FAULT,
        )

    def lookup(self, vpn: int, asid: int):
        matching = []

        for size_class in range(self.gen_params.vmem_params.max_tlb_size_class + 1):
            vpn_masked = vpn & self.size_class_mask(size_class)
            if (vpn_masked, asid) in self.translations:
                if self.translations[(vpn_masked, asid)][2] == size_class:
                    matching.append((*self.translations[(vpn_masked, asid)], False))
            if (vpn_masked, None) in self.translations:
                if self.translations[(vpn_masked, None)][2] == size_class:
                    matching.append((*self.translations[(vpn_masked, None)], True))

        if not matching:
            matching.append(
                (
                    0,
                    Permissions(),
                    0,
                    AddressTranslationLayouts.TLBResult.PAGE_FAULT,
                    0,
                )
            )

        return matching

    async def asid_get(self, sim: ProcessContext):
        async for *_, asid in sim.tick().sample(self.csr_instances.s_mode.satp_asid):  # type: ignore
            self.asid = asid

    @def_method_mock(lambda self: self.request_mock, enable=lambda self: not self.ready)
    def process_request(self, vpn, is_store):
        @MethodMock.effect
        def _():
            ppn, permissions, size_class, result, global_ = self.lookup(vpn, self.asid)[0]

            self.ready = True
            self.translated.append(
                {
                    "ppn": ppn,
                    "permissions": {
                        "r": permissions.r,
                        "w": permissions.w,
                        "x": permissions.x,
                        "u": permissions.u,
                        "d": permissions.d,
                        "g": global_,
                    },
                    "size_class": size_class,
                    "result": result,
                }
            )

    @def_method_mock(lambda self: self.accept_mock, enable=lambda self: self.ready)
    def process_accept(self):
        @MethodMock.effect
        def _():
            self.ready = False

        if self.translated:
            return self.translated[-1]

    def elaborate(self, platform):
        m = TModule()
        m.submodules += [self.request_mock, self.accept_mock]
        return m


class TestTLBCache(TestCaseWithSimulator):
    @pytest.fixture(autouse=True)
    def setup_method(self):
        self.gen_params = GenParams(
            configurations.test.replace(
                supervisor_mode=True,
                asidlen=4,
                supported_vm_schemes=(SatpMode.BARE, SatpMode.SV32),
                fetch_block_bytes_log=3,
            )
        )
        self.csr_instances = CSRInstances(self.gen_params)
        DependencyContext.get().add_dependency(CSRInstancesKey(), self.csr_instances)

        self.backing = MockTLBBackingDevice(self.gen_params)

        self.dut = SimpleTestCircuit(FullyAssociativeTLB(self.gen_params, entries=16, backing_resolver=self.backing))

        sfence_vma, _ = DependencyContext.get().get_dependency(SFenceVMAKey())
        self.sfence_vma = TestbenchIO(AdapterTrans.create(sfence_vma))

        self.m = ModuleConnector(
            dut=self.dut, sfence_vma=self.sfence_vma, backing=self.backing, csrs=self.csr_instances
        )

    def matches_lookup(self, response, vpn, asid):
        def entry_matches(e):
            e_ppn, e_permissions, e_size_class, e_result, e_global = e
            e_perm_dict = {
                "r": e_permissions.r,
                "w": e_permissions.w,
                "x": e_permissions.x,
                "u": e_permissions.u,
                "d": e_permissions.d,
                "g": e_global,
            }

            return all(
                (
                    response["result"] == e_result,
                    response["ppn"] == e_ppn,
                    response["size_class"] == e_size_class,
                    response["permissions"] == e_perm_dict,
                )
            )

        return any(entry_matches(e) for e in self.backing.lookup(vpn, asid))

    async def translation_is_cached_process(self, sim: TestbenchContext):
        vpn = 0x12345
        ppn = 0x23456
        asid = 3
        permissions = Permissions(r=1, w=1, x=0, u=1, d=1)

        self.backing.add_translation(vpn, ppn, permissions=permissions, asid=asid)
        sim.set(self.csr_instances.s_mode.satp_asid, asid)
        await sim.tick()

        await self.dut.request.call(sim, vpn=vpn, is_store=0)
        response = await self.dut.accept.call(sim)
        assert self.matches_lookup(response, vpn, asid)
        assert len(self.backing.translated) == 1

        await self.dut.request.call(sim, vpn=vpn, is_store=0)
        cached_response = await self.dut.accept.call(sim)
        assert self.matches_lookup(cached_response, vpn, asid)
        assert len(self.backing.translated) == 1

        # update entry and invalidate TLB
        ppn = 0x34567
        self.backing.add_translation(vpn, ppn, permissions=permissions, asid=asid)
        await self.sfence_vma.call(sim, vaddr=vpn << PAGE_SIZE_LOG, asid=asid, all_vaddrs=0, all_asids=0)
        await self.dut.request.call(sim, vpn=vpn, is_store=0)
        response_after_sfence = await self.dut.accept.call(sim)

        assert self.matches_lookup(response_after_sfence, vpn, asid)
        assert len(self.backing.translated) == 2

        # Additional sfence_vma variants and multi-entry cache tests
        # Prepare multiple entries across ASIDs
        base = len(self.backing.translated)

        vpn0 = 0x11111
        ppn0 = 0x22222
        vpn1 = 0x22222
        ppn1 = 0x33333
        vpn2 = 0x33333
        ppn2 = 0x44444

        asid_a = 7
        asid_b = 9

        self.backing.add_translation(vpn0, ppn0, permissions=permissions, asid=asid_a)
        self.backing.add_translation(vpn1, ppn1, permissions=permissions, asid=asid_a)
        self.backing.add_translation(vpn2, ppn2, permissions=permissions, asid=asid_b)

        # Cache vpn0 and vpn1 for asid_a
        sim.set(self.csr_instances.s_mode.satp_asid, asid_a)
        await sim.tick()

        await self.dut.request.call(sim, vpn=vpn0, is_store=0)
        _ = await self.dut.accept.call(sim)
        await self.dut.request.call(sim, vpn=vpn1, is_store=0)
        _ = await self.dut.accept.call(sim)
        assert len(self.backing.translated) == base + 2

        # Cache vpn2 for asid_b
        sim.set(self.csr_instances.s_mode.satp_asid, asid_b)
        await sim.tick()
        await self.dut.request.call(sim, vpn=vpn2, is_store=0)
        _ = await self.dut.accept.call(sim)
        assert len(self.backing.translated) == base + 3

        # Add a global (asid=None) entry and cache it. Global entries should
        # not be flushed by an sfence targeting a specific ASID.
        vpn_g = 0x44444
        ppn_g = 0x55555
        self.backing.add_translation(vpn_g, ppn_g, permissions=permissions, asid=None)
        sim.set(self.csr_instances.s_mode.satp_asid, asid_a)
        await sim.tick()
        await self.dut.request.call(sim, vpn=vpn_g, is_store=0)
        _ = await self.dut.accept.call(sim)
        assert len(self.backing.translated) == base + 4

        # 1) sfence for single vaddr+asid should only flush that mapping
        await self.sfence_vma.call(sim, vaddr=vpn0 << PAGE_SIZE_LOG, asid=asid_a, all_vaddrs=0, all_asids=0)
        sim.set(self.csr_instances.s_mode.satp_asid, asid_a)
        await sim.tick()

        # vpn0 should be re-translated
        await self.dut.request.call(sim, vpn=vpn0, is_store=0)
        _ = await self.dut.accept.call(sim)
        assert len(self.backing.translated) == base + 5

        # vpn1 for same ASID should still be cached
        await self.dut.request.call(sim, vpn=vpn1, is_store=0)
        _ = await self.dut.accept.call(sim)
        assert len(self.backing.translated) == base + 5

        # 2) sfence with all_vaddrs=1 and asid specified flushes all vaddrs for that ASID
        await self.sfence_vma.call(sim, vaddr=0, asid=asid_a, all_vaddrs=1, all_asids=0)
        sim.set(self.csr_instances.s_mode.satp_asid, asid_a)
        await sim.tick()

        await self.dut.request.call(sim, vpn=vpn1, is_store=0)
        _ = await self.dut.accept.call(sim)
        assert len(self.backing.translated) == base + 6

        # vpn2 for asid_b remains cached
        sim.set(self.csr_instances.s_mode.satp_asid, asid_b)
        await sim.tick()
        await self.dut.request.call(sim, vpn=vpn2, is_store=0)
        _ = await self.dut.accept.call(sim)
        assert len(self.backing.translated) == base + 6

        # 3) sfence with all_asids=1 and vaddr specified flushes that vaddr across all ASIDs
        await self.sfence_vma.call(sim, vaddr=vpn2 << PAGE_SIZE_LOG, asid=0, all_vaddrs=0, all_asids=1)
        sim.set(self.csr_instances.s_mode.satp_asid, asid_b)
        await sim.tick()
        await self.dut.request.call(sim, vpn=vpn2, is_store=0)
        _ = await self.dut.accept.call(sim)
        assert len(self.backing.translated) == base + 7

        # 4) sfence all (all_vaddrs=1, all_asids=1) flushes everything
        await self.sfence_vma.call(sim, vaddr=0, asid=0, all_vaddrs=1, all_asids=1)
        sim.set(self.csr_instances.s_mode.satp_asid, asid_a)
        await sim.tick()
        await self.dut.request.call(sim, vpn=vpn0, is_store=0)
        _ = await self.dut.accept.call(sim)
        assert len(self.backing.translated) == base + 8

    async def randomized_process(self, sim: TestbenchContext):
        # fill the backing device with random translations
        for _ in range(64):
            vpn = random.randint(0, 0xFFFFF)
            ppn = random.randint(0, 0xFFFFF)
            asid = random.randint(0, 0xF)
            rw = random.randint(0, 2)
            permissions = Permissions(
                r=1 * (rw >= 1),
                w=1 * (rw >= 2),
                x=random.randint(0, 1),
                u=random.randint(0, 1),
                d=random.randint(0, 1),
            )

            size_class = random.randint(0, self.gen_params.vmem_params.max_tlb_size_class)

            ppn = ppn & self.backing.size_class_mask(size_class)

            self.backing.add_translation(vpn, ppn, permissions=permissions, size_class=size_class, asid=asid)

        # add some access faults
        for _ in range(16):
            vpn = random.randint(0, 0xFFFFF)
            asid = random.randint(0, 0xF)
            self.backing.add_access_fault(vpn, asid=asid)

        test_cases = list(self.backing.translations.keys()) * 4
        test_cases.extend((random.randint(0, 0xFFFFF), random.randint(0, 0xF)) for _ in range(64))
        random.shuffle(test_cases)

        for vpn, asid in test_cases:
            sim.set(self.csr_instances.s_mode.satp_asid, asid)
            await sim.tick()

            await self.dut.request.call(sim, vpn=vpn, is_store=0)
            response = await self.dut.accept.call(sim)
            assert self.matches_lookup(response, vpn, asid)

        # check that we actually cached anything
        assert len(self.backing.translated) < len(test_cases)

    async def single_cycle_process(self, sim: TestbenchContext):
        vpn1 = 0xABCDE
        ppn1 = 0x1ABCD
        vpn2 = 0x12345
        ppn2 = 0x23456
        asid = 3
        permissions = Permissions(r=1, w=0, x=0, u=1, d=0)

        # Prime the cache by causing a miss and letting the backing fill it.
        self.backing.add_translation(vpn1, ppn1, permissions=permissions, asid=asid)
        self.backing.add_translation(vpn2, ppn2, permissions=permissions, asid=asid)
        sim.set(self.csr_instances.s_mode.satp_asid, asid)
        await sim.tick()

        # First access -> miss -> causes backing lookup and fills TLB
        await self.dut.request.call(sim, vpn=vpn1, is_store=0)
        _ = await self.dut.accept.call(sim)
        assert len(self.backing.translated) == 1
        await self.dut.request.call(sim, vpn=vpn2, is_store=0)
        _ = await self.dut.accept.call(sim)
        assert len(self.backing.translated) == 2

        # Immediately perform a second access without an intervening tick.
        # This should be serviced from the TLB in the same cycle and must
        # not trigger another backing lookup.
        req, cached = await CallTrigger(sim, [(self.dut.request, {"vpn": vpn1, "is_store": 0}), (self.dut.accept, {})])
        assert req is not None
        assert cached is not None
        assert self.matches_lookup(cached, vpn1, asid)

        # Immediately perform a third access to a different VPN, which should
        # also hit
        req, cached = await CallTrigger(sim, [(self.dut.request, {"vpn": vpn2, "is_store": 0}), (self.dut.accept, {})])
        assert req is not None
        assert cached is not None
        assert self.matches_lookup(cached, vpn2, asid)

        assert len(self.backing.translated) == 2

    def test_translation_is_cached(self):
        with self.run_simulation(self.m) as sim:
            sim.add_process(self.backing.asid_get)
            sim.add_mock(self.backing.process_request())
            sim.add_mock(self.backing.process_accept())
            sim.add_testbench(self.translation_is_cached_process)

    def test_randomized(self):
        with self.run_simulation(self.m) as sim:
            sim.add_process(self.backing.asid_get)
            sim.add_mock(self.backing.process_request())
            sim.add_mock(self.backing.process_accept())
            sim.add_testbench(self.randomized_process)

    def test_single_cycle_hit(self):
        with self.run_simulation(self.m) as sim:
            sim.add_process(self.backing.asid_get)
            sim.add_mock(self.backing.process_request())
            sim.add_mock(self.backing.process_accept())
            sim.add_testbench(self.single_cycle_process)
