import random
from dataclasses import dataclass
from typing import Optional
import pytest

from amaranth.utils import exact_log2

from transactron.testing import TestCaseWithSimulator, TestbenchContext, SimpleTestCircuit, def_method_mock, MethodMock
from transactron.utils import DependencyContext, ModuleConnector

from coreblocks.arch.isa_consts import PAGE_SIZE, PAGE_SIZE_LOG, SatpMode
from coreblocks.interface.keys import CSRInstancesKey
from coreblocks.interface.layouts import AddressTranslationLayouts
from coreblocks.params import GenParams, configurations
from coreblocks.priv.csr.csr_instances import CSRInstances
from coreblocks.priv.vmem.walker import PageTableWalker, PTELayout
from test.peripherals.bus_mock import BusMockParameters, MockMasterAdapter


@dataclass
class TranslationInfo:
    satp_ppn: int
    satp_mode: SatpMode
    vpn: int
    is_write: bool
    path: list[tuple[int, Optional[int]]]  # list of (PTE address, PTE value) pairs representing the translation path
    result: AddressTranslationLayouts.TLBResult
    ppn: Optional[int] = None
    permissions: Optional[int] = None
    # expected size class is determined by the length of the path
    pmp_failing: Optional[int] = None  # address to cause a PMP violation, if any


class TestPageTableWalker(TestCaseWithSimulator):
    @pytest.fixture(autouse=True)
    def setup_method(self):
        self.gen_params = GenParams(
            configurations.test.replace(
                supervisor_mode=True,
                asidlen=4,
                supported_vm_schemes=(SatpMode.BARE, SatpMode.SV32),
                pmp_register_count=16,
            )
        )
        self.layouts = self.gen_params.get(AddressTranslationLayouts)
        self.csr_instances = CSRInstances(self.gen_params)
        DependencyContext.get().add_dependency(CSRInstancesKey(), self.csr_instances)

        offset_bits = exact_log2(self.gen_params.isa.xlen // 8)
        self.bus = MockMasterAdapter(
            BusMockParameters(
                data_width=self.gen_params.isa.xlen, addr_width=self.gen_params.phys_addr_bits - offset_bits
            )
        )
        self.dut = SimpleTestCircuit(PageTableWalker(self.gen_params, self.bus))
        self.m = ModuleConnector(dut=self.dut, bus=self.bus, csrs=self.csr_instances)

        self.mem_ready = False
        self.mem_results = []
        self.mem_expected = []

    def gen_random_translation_path(self, mode: SatpMode) -> TranslationInfo:
        """
        Implementation of 'Virtual Address Translation Process' from RISC-V Privileged Spec.
        """

        translation_path = []

        vpn_len = self.gen_params.vmem_params.vpn_bits_for_mode(self.gen_params.isa.xlen, mode)
        vpn = random.randint(0, (1 << vpn_len) - 1)
        is_write = random.random() < 0.5

        def get_vpn_index(vpn, level):
            bits_per_level = SatpMode.bits_per_page_table_level(self.gen_params.isa.xlen)
            return (vpn >> (bits_per_level * level)) & ((1 << bits_per_level) - 1)

        pte_layout = PTELayout(self.gen_params)
        pte_size = pte_layout.as_shape().width // 8

        def encode_pte(fields_dict):
            return pte_layout.const(fields_dict).as_bits()

        max_ppn = ((1 << self.gen_params.phys_addr_bits) >> PAGE_SIZE_LOG) - 1
        root_ppn = random.randint(0, max_ppn)

        common = {
            "satp_ppn": root_ppn,
            "satp_mode": mode,
            "vpn": vpn,
            "is_write": is_write,
        }

        """1. Let a be satp.ppn×PAGESIZE, and let i=LEVELS-1."""
        a = root_ppn * PAGE_SIZE

        leaf_pte = None
        leaf_i = None
        for i in reversed(range(SatpMode.level_count(mode))):
            """2. Let pte be the value of the PTE at address a+va.vpn[i]×PTESIZE. (For Sv32, PTESIZE=4.)
            If accessing pte violates a PMA or PMP check, raise an access-fault exception corresponding
            to the original access type.
            """
            pte = a + (get_vpn_index(vpn, i) * pte_size)

            if random.random() < 0.05:  # 5% chance of PMP violation
                return TranslationInfo(
                    **common,
                    path=translation_path,
                    result=AddressTranslationLayouts.TLBResult.ACCESS_FAULT,
                    pmp_failing=pte,
                )

            if random.random() < 0.05:  # 5% chance of bus error
                return TranslationInfo(
                    **common,
                    path=translation_path + [(pte, None)],
                    result=AddressTranslationLayouts.TLBResult.ACCESS_FAULT,
                )

            """3. If pte.v=0, or if pte.r=0 and pte.w=1, or if any bits or encodings that are
            reserved for future standard use are set within pte, stop and raise a page-fault
            exception corresponding to the original access type.
            """

            # generate pte value
            if random.random() < 0.1:
                # generate any invalid PTE encoding
                bad_encodings = []
                bad_encodings.append({"V": 0})
                bad_encodings.append({"V": 1, "R": 0, "W": 1})
                for v in ("A", "D"):
                    bad_encodings.append({"V": 1, v: 1})  # non-leaf with A/D is reserved
                if self.gen_params.isa.xlen == 64:
                    bad_encodings.append({"V": 1, "reserved": random.randint(1, 0x7F)})
                    bad_encodings.append({"V": 1, "PBMT": random.randint(1, 3)})
                    bad_encodings.append({"V": 1, "N": 1})

                pte_dict = random.choice(bad_encodings)
                pte_dict["ppn"] = random.randint(0, max_ppn)

                translation_path.append((pte, encode_pte(pte_dict)))
                return TranslationInfo(
                    **common,
                    path=translation_path,
                    result=AddressTranslationLayouts.TLBResult.PAGE_FAULT,
                )

            """4. Otherwise, the PTE is valid. If pte.r=1 or pte.x=1, go to step 5.
            Otherwise, this PTE is a pointer to the next level of the page table.
            Let i=i-1. If i<0, stop and raise a page-fault exception corresponding to the original access type.
            Otherwise, let a=pte.ppn×PAGESIZE and go to step 2.
            """
            if random.random() < 0.5:
                leaf_pte = pte
                leaf_i = i
                break

            # non-leaf PTE
            ppn = random.randint(0, max_ppn)
            translation_path.append((pte, encode_pte({"V": 1, "ppn": ppn})))
            if i == 0:
                return TranslationInfo(
                    **common,
                    path=translation_path,
                    result=AddressTranslationLayouts.TLBResult.PAGE_FAULT,
                )
            a = ppn * PAGE_SIZE

        # leaf PTE
        assert leaf_pte is not None
        assert leaf_i is not None

        rw = random.randint(0, 2)

        pte_dict = {
            "V": 1,
            "R": rw >= 1,
            "W": rw == 2,
            "X": rw == 0 or (random.random() < 0.3),
            "U": random.random() < 0.5,
            "A": random.random() < 0.9,
            "D": random.random() < 0.5,
            "G": random.random() < 0.5,
            "RSW": random.randint(0, 3),
        }

        level_bits = SatpMode.bits_per_page_table_level(self.gen_params.isa.xlen) * leaf_i
        upper_ppn = random.randint(0, max_ppn >> level_bits)

        """5. A leaf PTE has been reached. If i>0 and pte.ppn[i-1:0] ≠ 0, this is a misaligned superpage;
        stop and raise a page-fault exception corresponding to the original access type.
        """
        if leaf_i > 0 and random.random() < 0.1:  # 10% chance of misaligned superpage
            lower_ppn = random.randint(1, (1 << level_bits) - 1)  # ensure misalignment
            ppn = (upper_ppn << level_bits) | lower_ppn
            translation_path.append((leaf_pte, encode_pte({**pte_dict, "ppn": ppn})))
            return TranslationInfo(
                **common,
                path=translation_path,
                result=AddressTranslationLayouts.TLBResult.PAGE_FAULT,
            )

        pte_dict["ppn"] = upper_ppn << level_bits
        translation_path.append((leaf_pte, encode_pte(pte_dict)))

        if pte_dict["A"] == 0 or (is_write and pte_dict["D"] == 0):
            # if A=0 or if it's a store and D=0, Svade treats it as a page fault
            return TranslationInfo(
                **common,
                path=translation_path,
                result=AddressTranslationLayouts.TLBResult.PAGE_FAULT,
            )

        permissions = {
            "r": pte_dict["R"],
            "w": pte_dict["W"],
            "x": pte_dict["X"],
            "u": pte_dict["U"],
            "d": pte_dict["D"],
            "g": pte_dict["G"],
        }

        return TranslationInfo(
            **common,
            path=translation_path,
            result=AddressTranslationLayouts.TLBResult.HIT,
            ppn=pte_dict["ppn"],
            permissions=self.layouts.permissions.const(permissions).as_bits(),  # type: ignore
        )

    @def_method_mock(lambda self: self.bus.request_read_mock, enable=lambda self: not self.mem_ready)
    def bus_read_req_proc(self, addr, sel):
        @MethodMock.effect
        def _():
            assert len(self.mem_expected) > 0

            expected_addr, data = self.mem_expected.pop(0)
            off_bits = exact_log2(self.gen_params.isa.xlen // 8)

            b_addr = addr << off_bits

            assert sel == 0xFF if self.gen_params.isa.xlen == 64 else 0xF
            assert b_addr == expected_addr
            if data is None:
                self.mem_results.append(
                    {
                        "data": 0,
                        "err": 1,
                    }
                )
            else:
                self.mem_results.append(
                    {
                        "data": data,
                        "err": 0,
                    }
                )
            self.mem_ready = True

    @def_method_mock(lambda self: self.bus.get_read_response_mock, enable=lambda self: self.mem_ready)
    def bus_read_resp_proc(self):
        @MethodMock.effect
        def _():
            self.mem_ready = False

        if self.mem_results:
            return self.mem_results[-1]

    async def random_translations_process(self, sim: TestbenchContext):
        # allow PMP for S-mode
        sim.set(self.csr_instances.m_mode.pmpxcfg[6].value, 0b00001001)  # R=1, A=TOR
        sim.set(self.csr_instances.m_mode.pmpaddrx[5].value, 0)
        sim.set(self.csr_instances.m_mode.pmpaddrx[6].value, ~0)

        for _ in range(128):
            mode = random.choice([*self.gen_params.vmem_params.supported_non_bare_schemes])
            translation_info = self.gen_random_translation_path(mode)

            sim.set(self.csr_instances.s_mode.satp_mode, translation_info.satp_mode)
            sim.set(self.csr_instances.s_mode.satp_ppn, translation_info.satp_ppn)

            # clean PPM
            if translation_info.pmp_failing is not None:
                sim.set(self.csr_instances.m_mode.pmpxcfg[1].value, 0b00001000)  # RWX=0, A=TOR
                pmp_addr = translation_info.pmp_failing >> 2
                pnp_top = (translation_info.pmp_failing + self.gen_params.pmp_grain_bytes) >> 2

                sim.set(self.csr_instances.m_mode.pmpaddrx[0].value, pmp_addr)
                sim.set(self.csr_instances.m_mode.pmpaddrx[1].value, pnp_top)
            else:
                sim.set(self.csr_instances.m_mode.pmpxcfg[0].value, 0)

            self.mem_expected = translation_info.path.copy()
            self.mem_results = []
            self.mem_ready = False

            await sim.tick()
            await self.dut.request.call(sim, vpn=translation_info.vpn, is_store=translation_info.is_write)
            ret = await self.dut.accept.call(sim)
            assert not self.mem_expected

            assert ret.result == translation_info.result
            if translation_info.result == AddressTranslationLayouts.TLBResult.HIT:
                assert ret.ppn == translation_info.ppn
                assert ret.permissions.as_bits() == translation_info.permissions
                assert ret.size_class == SatpMode.level_count(translation_info.satp_mode) - len(translation_info.path)

    def test_random_translations(self):
        with self.run_simulation(self.m) as sim:
            self.add_mock(sim, self.bus_read_req_proc())  # type: ignore
            self.add_mock(sim, self.bus_read_resp_proc())  # type: ignore
            sim.add_testbench(self.random_translations_process)
