import random
from typing import Optional

from attr import dataclass
from parameterized import parameterized_class

from amaranth import *

import pytest
from transactron import *
from transactron.lib import Adapter
from transactron.utils import DependencyContext, ModuleConnector
from transactron.testing import (
    ProcessContext,
    TestCaseWithSimulator,
    TestbenchContext,
    TestbenchIO,
    def_method_mock,
    SimpleTestCircuit,
    MethodMock,
)

from coreblocks.arch.isa_consts import SatpMode
from coreblocks.interface.keys import CSRInstancesKey
from coreblocks.interface.layouts import AddressTranslationLayouts
from coreblocks.params import GenParams, configurations
from coreblocks.priv.csr.csr_instances import CSRInstances
from coreblocks.priv.vmem.iface import TLBBackingDevice
from coreblocks.priv.vmem.tlb import FullyAssociativeTLB, SetAssociativeTLB


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
            matching.append((
                0,
                Permissions(),
                0,
                AddressTranslationLayouts.TLBResult.PAGE_FAULT,
                0,
            ))

        return matching

    async def asid_get(self, sim: ProcessContext):
        async for *_, asid in (
            sim.tick().sample(self.csr_instances.s_mode.satp_asid)  # type: ignore
        ):
            self.asid = asid

    @def_method_mock(lambda self: self.request_mock, enable=lambda self: not self.ready)
    def process_request(self, vpn, write_aspect):
        @MethodMock.effect
        def _():
            ppn, permissions, size_class, result, global_ = self.lookup(vpn, self.asid)[0]

            self.ready = True
            self.translated.append({
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
            })

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


@parameterized_class(
    ("name",),
    [
        ("fully_associative",),
        ("set_associative",),
    ],
)
class TestTLBCache(TestCaseWithSimulator):
    name: str

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

        if self.name == "fully_associative":
            dut = FullyAssociativeTLB(self.gen_params, entries=16, backing_resolver=self.backing)
        elif self.name == "set_associative":
            dut = SetAssociativeTLB(
                self.gen_params,
                ways=4,
                entries=16,
                backing_resolver=self.backing,
            )
        else:
            print(self.name)
            assert False, "Invalid TLB type"

        self.dut = SimpleTestCircuit(dut)

        self.m = ModuleConnector(self.dut, backing=self.backing, csrs=self.csr_instances)

    def assert_hit(
        self,
        response,
        *,
        ppn: int,
        permissions: Permissions,
        size_class: int = 0,
        global_entry: bool = False,
    ):
        assert response["result"] == AddressTranslationLayouts.TLBResult.HIT
        assert response["ppn"] == ppn
        assert response["size_class"] == size_class
        assert response["permissions"] == {
            "r": permissions.r,
            "w": permissions.w,
            "x": permissions.x,
            "u": permissions.u,
            "d": permissions.d,
            "g": global_entry,
        }

    async def set_satp_asid(self, sim: TestbenchContext, asid: int):
        await sim.tick()

    async def translation_is_cached_process(self, sim: TestbenchContext):
        vpn = 0x12345
        ppn = 0x23456
        asid = 3
        permissions = Permissions(r=1, w=1, x=0, u=1, d=1)

        self.backing.add_translation(vpn, ppn, permissions=permissions, asid=asid)
        sim.set(self.csr_instances.s_mode.satp_asid, asid)
        await sim.tick()

        await self.dut.request.call(sim, vpn=vpn, write_aspect=0)
        response = await self.dut.accept.call(sim)
        self.assert_hit(response, ppn=ppn, permissions=permissions)
        assert len(self.backing.translated) == 1

        await self.dut.request.call(sim, vpn=vpn, write_aspect=0)
        cached_response = await self.dut.accept.call(sim)
        self.assert_hit(cached_response, ppn=ppn, permissions=permissions)
        assert len(self.backing.translated) == 1

    async def randomized_process(self, sim: TestbenchContext):
        # fill the backing device with random translations
        for _ in range(128):
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

        def matches_lookup(response, expected):
            expected_ppn, expected_permissions, expected_size_class, expected_result, expected_global = expected

            if response["result"] != expected_result:
                return False
            if response["ppn"] != expected_ppn:
                return False
            if response["size_class"] != expected_size_class:
                return False
            if response["permissions"] != {
                "r": expected_permissions.r,
                "w": expected_permissions.w,
                "x": expected_permissions.x,
                "u": expected_permissions.u,
                "d": expected_permissions.d,
                "g": expected_global,
            }:
                return False
            return True

        # check that each vpn in the backing device is translated correctly
        for (vpn, asid) in self.backing.translations.keys():
            sim.set(self.csr_instances.s_mode.satp_asid, asid if asid is not None else 0xF)
            await sim.tick()

            await self.dut.request.call(sim, vpn=vpn, write_aspect=random.randint(0, 1))
            response = await self.dut.accept.call(sim)
            matches = self.backing.lookup(vpn, asid if asid is not None else 0xF)
            print(f"VPN: {vpn:X}, ASID: {asid}")
            # print response and matches for debugging
            print(f"Response: {response.ppn:x}, {response.permissions.r}{response.permissions.w}{response.permissions.x}{response.permissions.u}{response.permissions.d}, {response.size_class}, {response.result}")
            print("Matches:")
            for match in matches:
                print(f"{match[0]:x}, {match[1].r}{match[1].w}{match[1].x}{match[1].u}{match[1].d}, {match[2]}, {match[3]}, global={match[4]}")

            assert any(matches_lookup(response, expected) for expected in matches)

        # check some random VPNs that are not in the backing device to ensure they cause page faults
        for _ in range(128):
            vpn = random.randint(0, 0xFFFFF)
            asid = random.randint(0, 0xF)

            sim.set(self.csr_instances.s_mode.satp_asid, asid)
            await sim.tick()

            await self.dut.request.call(sim, vpn=vpn, write_aspect=random.randint(0, 1))
            response = await self.dut.accept.call(sim)
            matches = self.backing.lookup(vpn, asid)

            assert any(matches_lookup(response, expected) for expected in matches)

    def test_translation_is_cached(self):
        with self.run_simulation(self.m) as sim:
            sim.add_process(self.backing.asid_get)
            self.add_mock(sim, self.backing.process_request())  # type: ignore
            self.add_mock(sim, self.backing.process_accept())  # type: ignore
            sim.add_testbench(self.translation_is_cached_process)

    def test_randomized(self):
        with self.run_simulation(self.m) as sim:
            sim.add_process(self.backing.asid_get)
            self.add_mock(sim, self.backing.process_request())  # type: ignore
            self.add_mock(sim, self.backing.process_accept())  # type: ignore
            sim.add_testbench(self.randomized_process)
