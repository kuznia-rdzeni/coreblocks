"""Unit tests for TLB implementations (FullyAssociativeTLB and SetAssociativeTLB)."""

from typing import Optional

from attr import dataclass
from parameterized import parameterized_class

from amaranth import *

from transactron import *
from transactron.lib import Adapter, AdapterTrans
from transactron.testing import (
    TestCaseWithSimulator,
    TestbenchContext,
    TestbenchIO,
    def_method_mock,
    MethodMock,
)
from transactron.utils import DependencyContext

from coreblocks.arch.isa_consts import PAGE_SIZE_LOG, SatpMode
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
        self.layout = gen_params.get(AddressTranslationLayouts)

        self.request_mock = TestbenchIO(Adapter(i=self.layout.tlb_request))
        self.accept_mock = TestbenchIO(Adapter(o=self.layout.tlb_accept))

        self.request = self.request_mock.adapter.iface
        self.accept = self.accept_mock.adapter.iface

        # Storage for mock translations: (vpn, asid) -> (ppn, permissions, size_class, result)
        self.translations = dict()
        self.request_count = 0
        self.accept_count = 0

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

    def elaborate(self, platform):
        m = TModule()

        m.submodules.request_mock = request_mock = self.request_mock
        m.submodules.accept_mock = accept_mock = self.accept_mock

        bits_per_size_class = self.gen_params.vmem_params.page_table_level_bits

        results = [{
            "result": AddressTranslationLayouts.TLBResult.PAGE_FAULT,
            "ppn": 0,
            "permissions": Permissions(),
            "size_class": 0,
        }]
        requested = False

        @def_method_mock(lambda: request_mock, enable=lambda: not requested)
        def process_request(vpn: int, asid: int):
            found_key = None

            for size_class in range(self.gen_params.vmem_params.max_tlb_size_class + 1):
                mask = (1 << bits_per_size_class * size_class) - 1
                vpn_masked = vpn & ~mask
                if (vpn_masked, asid) in self.translations:
                    found_key = (vpn_masked, asid)
                    break
                if (vpn_masked, None) in self.translations:
                    found_key = (vpn_masked, None)
                    break

            ret_val = None

            if found_key is None:
                ret_val = {
                    "result": AddressTranslationLayouts.TLBResult.PAGE_FAULT,
                    "ppn": 0,
                    "permissions": Permissions(),
                    "size_class": 0,
                }
            else:
                ppn, permissions, size_class, result = self.translations[found_key]

                ret_val = {
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

            @MethodMock.effect
            def eff():
                nonlocal requested
                requested = True
                self.request_count += 1
                results.append(ret_val)

        @def_method_mock(lambda: accept_mock, enable=lambda: requested)
        def process_accept():
            @MethodMock.effect
            def eff():
                nonlocal requested
                requested = False
                self.accept_count += 1

            return results[-1]

        return m


class TLBTestCircuit(Elaboratable):
    def __init__(self, gen_params: GenParams, dut_kind: str):
        self.gen_params = gen_params
        self.dut_kind = dut_kind

    def create_dut(self, backing: TLBBackingDevice) -> Elaboratable:
        if self.dut_kind == "fully_associative":
            return FullyAssociativeTLB(self.gen_params, entries=4, backing_resolver=backing)

        if self.dut_kind == "set_associative":
            return SetAssociativeTLB(self.gen_params, entries=4, ways=2, backing_resolver=backing)

        raise ValueError(f"Unknown TLB kind: {self.dut_kind}")

    def elaborate(self, platform):
        m = TModule()

        self.csr_instances = CSRInstances(self.gen_params)
        DependencyContext.get().add_dependency(CSRInstancesKey(), self.csr_instances)

        self.backing = MockTLBBackingDevice(self.gen_params)
        self.dut = self.create_dut(self.backing)

        m.submodules.csr_instances = self.csr_instances
        m.submodules.backing = self.backing
        m.submodules.dut = self.dut
        m.submodules.request = self.request = TestbenchIO(AdapterTrans.create(self.dut.request))
        m.submodules.accept = self.accept = TestbenchIO(AdapterTrans.create(self.dut.accept))

        return m


@parameterized_class(
    ("name", "dut_kind"),
    [
        ("fully_associative", "fully_associative"),
        ("set_associative", "set_associative"),
    ],
)
class TestTLBCache(TestCaseWithSimulator):
    dut_kind: str

    def setup_method(self):
        self.gen_params = GenParams(
            configurations.test.replace(
                xlen=64,
                supervisor_mode=True,
                asidlen=4,
                supported_vm_schemes=(SatpMode.BARE, SatpMode.SV39),
                fetch_block_bytes_log=3,
            )
        )
        self.tc = TLBTestCircuit(self.gen_params, self.dut_kind)

    def assert_hit(self, response, *, ppn: int, permissions: Permissions, size_class: int = 0, global_entry: bool = False):
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
        sim.set(self.tc.csr_instances.s_mode.satp_asid.value, asid)
        await sim.tick()

    async def translation_is_cached_process(self, sim: TestbenchContext):
        vpn = 0x12345 & ((1 << self.gen_params.vmem_params.max_tlb_vpn_bits) - 1)
        ppn = 0x23456 & ((1 << (self.gen_params.phys_addr_bits - PAGE_SIZE_LOG)) - 1)
        asid = 3
        permissions = Permissions(r=1, w=1, x=0, u=1, d=1)

        self.tc.backing.add_translation(vpn, ppn, permissions=permissions, asid=asid)
        await self.set_satp_asid(sim, asid)

        await self.tc.request.call(sim, vpn=vpn, write_aspect=0)
        response = await self.tc.accept.call(sim)
        self.assert_hit(response, ppn=ppn, permissions=permissions)
        assert self.tc.backing.request_count == 1

        await self.tc.request.call(sim, vpn=vpn, write_aspect=0)
        cached_response = await self.tc.accept.call(sim)
        self.assert_hit(cached_response, ppn=ppn, permissions=permissions)
        assert self.tc.backing.request_count == 1

    async def access_fault_is_forwarded_process(self, sim: TestbenchContext):
        vpn = 0x5A5A & ((1 << self.gen_params.vmem_params.max_tlb_vpn_bits) - 1)
        asid = 2

        self.tc.backing.add_access_fault(vpn, asid=asid)
        await self.set_satp_asid(sim, asid)

        await self.tc.request.call(sim, vpn=vpn, write_aspect=0)
        response = await self.tc.accept.call(sim)

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
        assert self.tc.backing.request_count == 1

    def test_translation_is_cached(self):
        with self.run_simulation(self.tc) as sim:
            sim.add_testbench(self.translation_is_cached_process)

    def test_access_fault_is_forwarded(self):
        with self.run_simulation(self.tc) as sim:
            sim.add_testbench(self.access_fault_is_forwarded_process)
