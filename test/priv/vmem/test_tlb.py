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
        size_class_mask = -(1 << (self.gen_params.vmem_params.page_table_level_bits * size_class))
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

    async def asid_get(self, sim: ProcessContext):
        async for *_, asid in sim.tick().sample(self.csr_instances.s_mode.satp_asid):  # type: ignore
            self.asid = asid

    @def_method_mock(lambda self: self.request_mock, enable=lambda self: not self.ready)
    def process_request(self, vpn, write_aspect):
        @MethodMock.effect
        def _():
            found_key = None

            bits_per_size_class = self.gen_params.vmem_params.page_table_level_bits

            for size_class in range(self.gen_params.vmem_params.max_tlb_size_class + 1):
                mask = (1 << (bits_per_size_class * size_class)) - 1
                vpn_masked = vpn & ~mask
                if (vpn_masked, self.asid) in self.translations:
                    found_key = (vpn_masked, self.asid)
                    break
                if (vpn_masked, None) in self.translations:
                    found_key = (vpn_masked, None)
                    break

            if found_key is None:
                res_dict = {
                    "result": AddressTranslationLayouts.TLBResult.PAGE_FAULT,
                    "ppn": 0,
                    "permissions": {
                        "r": 0,
                        "w": 0,
                        "x": 0,
                        "u": 0,
                        "d": 0,
                        "g": 0,
                    },
                    "size_class": 0,
                }
            else:
                ppn, permissions, size_class, result = self.translations[found_key]
                res_dict = {
                    "result": result,
                    "ppn": ppn,
                    "permissions": {
                        "r": permissions.r,
                        "w": permissions.w,
                        "x": permissions.x,
                        "u": permissions.u,
                        "d": permissions.d,
                        "g": found_key[1] is None,
                    },
                    "size_class": size_class,
                }

            self.ready = True
            print("!!!")
            self.translated.append(res_dict)

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
            dut = SetAssociativeTLB(self.gen_params, ways=4, entries=16, backing_resolver=self.backing)
        else:
            print(self.name)
            assert False, "Invalid TLB type"

        self.dut = SimpleTestCircuit(dut)

        self.m = ModuleConnector(self.dut, backing=self.backing, csrs=self.csr_instances)

    def assert_hit(
        self, response, *, ppn: int, permissions: Permissions, size_class: int = 0, global_entry: bool = False
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

        print("Starting translation_is_cached_process")
        await self.dut.request.call(sim, vpn=vpn, write_aspect=0)
        print("Requested translation")
        response = await self.dut.accept.call(sim)
        print("Received response")
        self.assert_hit(response, ppn=ppn, permissions=permissions)
        assert len(self.backing.translated) == 1

        print("Requesting translation again to test caching")
        await self.dut.request.call(sim, vpn=vpn, write_aspect=0)
        print("Requested translation again")
        cached_response = await self.dut.accept.call(sim)
        print("Received cached response")
        self.assert_hit(cached_response, ppn=ppn, permissions=permissions)
        assert len(self.backing.translated) == 1

    async def access_fault_is_forwarded_process(self, sim: TestbenchContext):
        vpn = 0x5A5A
        asid = 2

        self.backing.add_access_fault(vpn, asid=asid)
        sim.set(self.csr_instances.s_mode.satp_asid, asid)

        await self.dut.request.call(sim, vpn=vpn, write_aspect=0)
        response = await self.dut.accept.call(sim)

        assert response["result"] == AddressTranslationLayouts.TLBResult.ACCESS_FAULT
        assert response["ppn"] == 0
        assert response["size_class"] == 0
        assert response["permissions"] == {
            "r": 0,
            "w": 0,
            "x": 0,
            "u": 0,
            "d": 0,
            "g": False,
        }

    def test_translation_is_cached(self):
        with self.run_simulation(self.m, max_cycles=300) as sim:
            sim.add_process(self.backing.asid_get)
            self.add_mock(sim, self.backing.process_request())  # type: ignore
            self.add_mock(sim, self.backing.process_accept())  # type: ignore
            sim.add_testbench(self.translation_is_cached_process)

    def test_access_fault_is_forwarded(self):
        with self.run_simulation(self.m, max_cycles=300) as sim:
            sim.add_process(self.backing.asid_get)
            self.add_mock(sim, self.backing.process_request())  # type: ignore
            self.add_mock(sim, self.backing.process_accept())  # type: ignore
            sim.add_testbench(self.access_fault_is_forwarded_process)
