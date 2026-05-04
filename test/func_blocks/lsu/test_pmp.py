from dataclasses import dataclass
import pytest
from coreblocks.arch.isa_consts import PMPAFlagEncoding, PrivilegeLevel, PMPCfgLayout
from coreblocks.params import GenParams
from coreblocks.params import configurations
from coreblocks.interface.keys import CSRInstancesKey
from transactron.lib.adapters import AdapterTrans
from transactron.testing import TestbenchIO
from coreblocks.priv.csr.csr_instances import CSRInstances
from transactron.testing import TestbenchContext, TestCaseWithSimulator
from transactron.utils.amaranth_ext.elaboratables import ModuleConnector
from transactron.utils.dependencies import DependencyContext
from coreblocks.priv.pmp import PMPChecker, PMPOperationMode


def make_cfg(*, r=0, w=0, x=0, a=0, lock=0) -> int:
    cfg = PMPCfgLayout().const({"R": r, "W": w, "X": x, "A": a, "L": lock})
    return cfg.as_value().value


@dataclass
class PMPEntry:
    addr: int
    cfg: int


@dataclass
class PMPCheck:
    addr: int
    r: int  # expected read permission (0 = denied, 1 = allowed)
    w: int  # expected write permission (0 = denied, 1 = allowed)
    x: int  # expected execute permission (0 = denied, 1 = allowed)


class TestPMPDirect(TestCaseWithSimulator):
    @pytest.fixture(autouse=True)
    def setup(self, fixture_initialize_testing_env):
        pass

    def run_pmp_test(
        self,
        entries: list[PMPEntry],
        checks: list[PMPCheck],
        priv_mode=PrivilegeLevel.USER,
        pmp_mode=PMPOperationMode.LSU,
        mprv=0,
        mpp=PrivilegeLevel.USER,
        pmp_grain_log=2,
        icache_enable=False,
    ):
        gen_params = GenParams(
            configurations.test.replace(pmp_register_count=16, pmp_grain_log=pmp_grain_log, icache_enable=icache_enable)
        )
        csr = CSRInstances(gen_params)
        DependencyContext.get().add_dependency(CSRInstancesKey(), csr)
        pmp = PMPChecker(gen_params, mode=pmp_mode)
        test_module = ModuleConnector(csr_instances=csr, pmp=pmp)

        async def process(sim: TestbenchContext):
            sim.set(csr.m_mode.priv_mode.value, priv_mode)
            sim.set(csr.m_mode.mstatus_mprv.value, mprv)
            sim.set(csr.m_mode.mstatus_mpp.value, mpp)
            for i, entry in enumerate(entries):
                sim.set(csr.m_mode.pmpaddrx[i].value, entry.addr)
                sim.set(csr.m_mode.pmpxcfg[i].value, entry.cfg)

            for c in checks:
                sim.set(pmp.paddr, c.addr)
                result = sim.get(pmp.result)
                assert result.r == c.r, f"addr=0x{c.addr:08x}: expected r={c.r}, got {result.r}"
                assert result.w == c.w, f"addr=0x{c.addr:08x}: expected w={c.w}, got {result.w}"
                assert result.x == c.x, f"addr=0x{c.addr:08x}: expected x={c.x}, got {result.x}"

        with self.run_simulation(test_module) as sim:
            sim.add_testbench(process)

    @pytest.mark.parametrize("pmp_grain_log", [2, 3, 4])
    def test_mmode_no_entries(self, pmp_grain_log):
        self.run_pmp_test(
            [],
            [PMPCheck(0x1000, 1, 1, 1), PMPCheck(0xDEAD, 1, 1, 1)],
            priv_mode=PrivilegeLevel.MACHINE,
            pmp_mode=PMPOperationMode.INSTRUCTION_FETCH,
            pmp_grain_log=pmp_grain_log,
        )

    @pytest.mark.parametrize("pmp_grain_log", [2, 3, 4])
    def test_umode_no_entries(self, pmp_grain_log):
        self.run_pmp_test([], [PMPCheck(0x1000, 0, 0, 0), PMPCheck(0xDEAD, 0, 0, 0)], pmp_grain_log=pmp_grain_log)

    @pytest.mark.parametrize("pmp_grain_log", [2, 3, 4])
    def test_lsu_mode_honors_mprv(self, pmp_grain_log):
        # In LSU mode, MPRV redirects machine-mode memory accesses through MPP.
        self.run_pmp_test(
            [],
            [PMPCheck(0x1000, 0, 0, 0), PMPCheck(0xDEAD, 0, 0, 0)],
            priv_mode=PrivilegeLevel.MACHINE,
            pmp_mode=PMPOperationMode.LSU,
            mprv=1,
            mpp=PrivilegeLevel.USER,
            pmp_grain_log=pmp_grain_log,
        )

    @pytest.mark.parametrize("pmp_grain_log", [2, 3, 4])
    def test_fetch_mode_ignores_mprv(self, pmp_grain_log):
        # Fetch checks use current privilege mode only and ignore MPRV.
        self.run_pmp_test(
            [],
            [PMPCheck(0x1000, 1, 1, 1), PMPCheck(0xDEAD, 1, 1, 1)],
            priv_mode=PrivilegeLevel.MACHINE,
            pmp_mode=PMPOperationMode.INSTRUCTION_FETCH,
            mprv=1,
            mpp=PrivilegeLevel.USER,
            pmp_grain_log=pmp_grain_log,
        )

    @pytest.mark.parametrize("pmp_grain_log", [2, 3, 4])
    def test_mmu_mode_forces_supervisor(self, pmp_grain_log):
        # MMU checks are always evaluated as-if in supervisor mode.
        self.run_pmp_test(
            [],
            [PMPCheck(0x1000, 0, 0, 0), PMPCheck(0xDEAD, 0, 0, 0)],
            priv_mode=PrivilegeLevel.MACHINE,
            pmp_mode=PMPOperationMode.MMU,
            pmp_grain_log=pmp_grain_log,
        )

    @pytest.mark.parametrize("pmp_grain_log", [2, 3, 4])
    def test_priority(self, pmp_grain_log):
        self.run_pmp_test(
            [
                PMPEntry(addr=0x2000 >> 2, cfg=make_cfg(r=1, a=PMPAFlagEncoding.TOR)),
                PMPEntry(addr=0x4000 >> 2, cfg=make_cfg(r=1, w=1, a=PMPAFlagEncoding.TOR)),
            ],
            [
                PMPCheck(0x1000, 1, 0, 0),
                PMPCheck(0x3000, 1, 1, 0),
            ],
            pmp_grain_log=pmp_grain_log,
        )

    @pytest.mark.parametrize("pmp_grain_log", [2, 3, 4])
    def test_locked_mmode(self, pmp_grain_log):
        self.run_pmp_test(
            [PMPEntry(addr=0x2000 >> 2, cfg=make_cfg(lock=1, a=PMPAFlagEncoding.TOR))],
            [PMPCheck(0x1000, 0, 0, 0)],
            priv_mode=PrivilegeLevel.MACHINE,
            pmp_grain_log=pmp_grain_log,
        )

    @pytest.mark.parametrize("pmp_grain_log", [2, 3, 4])
    def test_unlocked_mmode(self, pmp_grain_log):
        self.run_pmp_test(
            [PMPEntry(addr=0x2000 >> 2, cfg=make_cfg(a=PMPAFlagEncoding.TOR))],
            [PMPCheck(0x1000, 1, 1, 1)],
            priv_mode=PrivilegeLevel.MACHINE,
            pmp_grain_log=pmp_grain_log,
        )

    @pytest.mark.parametrize("pmp_grain_log", [2, 3, 4])
    def test_tor_basic(self, pmp_grain_log):
        # Lower bound is 0 when no previous entry
        # Range: [0x0, 0x2000)
        self.run_pmp_test(
            [PMPEntry(addr=0x2000 >> 2, cfg=make_cfg(r=1, w=1, a=PMPAFlagEncoding.TOR))],
            [
                PMPCheck(0x0000, 1, 1, 0),
                PMPCheck(0x1000, 1, 1, 0),
                PMPCheck(0x1FFC, 1, 1, 0),
                PMPCheck(0x2000, 0, 0, 0),
                PMPCheck(0x9000, 0, 0, 0),
            ],
            pmp_grain_log=pmp_grain_log,
        )

    @pytest.mark.parametrize("pmp_grain_log", [2, 3, 4])
    def test_tor_range(self, pmp_grain_log):
        # Entry i-1 sets lower bound for Entry i (TOR)
        # Range: [0x1000, 0x2000)
        self.run_pmp_test(
            [
                PMPEntry(addr=0x1000 >> 2, cfg=make_cfg(a=PMPAFlagEncoding.OFF)),
                PMPEntry(addr=0x2000 >> 2, cfg=make_cfg(r=1, x=1, a=PMPAFlagEncoding.TOR)),
            ],
            [
                PMPCheck(0x0800, 0, 0, 0),
                PMPCheck(0x1000, 1, 0, 1),
                PMPCheck(0x1800, 1, 0, 1),
                PMPCheck(0x2000, 0, 0, 0),
                PMPCheck(0x3000, 0, 0, 0),
            ],
            pmp_grain_log=pmp_grain_log,
        )

    @pytest.mark.parametrize("pmp_grain_log", [2, 3, 4])
    def test_tor_no_perms(self, pmp_grain_log):
        self.run_pmp_test(
            [PMPEntry(addr=0x2000 >> 2, cfg=make_cfg(a=PMPAFlagEncoding.TOR))],
            [PMPCheck(0x1000, 0, 0, 0)],
            pmp_grain_log=pmp_grain_log,
        )

    def test_tor_smaller_than_grain(self):
        # TOR range [0x100, 0x110) = 16 bytes
        # Grain = 64 bytes, bigger than TOR -> empty range
        self.run_pmp_test(
            [
                PMPEntry(addr=0x40, cfg=make_cfg(a=PMPAFlagEncoding.OFF)),
                PMPEntry(addr=0x44, cfg=make_cfg(r=1, w=1, a=PMPAFlagEncoding.TOR)),
            ],
            [
                PMPCheck(0x100, 0, 0, 0),
                PMPCheck(0x10C, 0, 0, 0),
                PMPCheck(0x110, 0, 0, 0),
            ],
            pmp_grain_log=6,
        )

    def test_na4(self):
        self.run_pmp_test(
            [PMPEntry(addr=0x1000 >> 2, cfg=make_cfg(r=1, w=1, a=PMPAFlagEncoding.NA4))],
            [
                PMPCheck(0x1000, 1, 1, 0),
                PMPCheck(0x1001, 1, 1, 0),
                PMPCheck(0x1002, 1, 1, 0),
                PMPCheck(0x1003, 1, 1, 0),
                PMPCheck(0x1004, 0, 0, 0),
                PMPCheck(0x0FFC, 0, 0, 0),
            ],
        )

    @pytest.mark.parametrize("pmp_grain_log", [3, 4])
    def test_na4_disabled_with_grain(self, pmp_grain_log):
        # NA4 is treated as OFF when grain > 0
        self.run_pmp_test(
            [PMPEntry(addr=0x1000 >> 2, cfg=make_cfg(r=1, w=1, a=PMPAFlagEncoding.NA4))],
            [PMPCheck(0x1000, 0, 0, 0), PMPCheck(0x1001, 0, 0, 0)],
            pmp_grain_log=pmp_grain_log,
        )

    @pytest.mark.parametrize("pmp_grain_log", [2, 3, 4])
    def test_napot(self, pmp_grain_log):
        # pmpaddr=0x43F -> 6 trailing ones (0x3F) -> 2^(6+3) = 512B
        # base = (0x43F & ~0x3F) << 2 = 0x1000
        # Range: [0x1000, 0x11FF]
        self.run_pmp_test(
            [PMPEntry(addr=0x43F, cfg=make_cfg(r=1, x=1, a=PMPAFlagEncoding.NAPOT))],
            [
                PMPCheck(0x1000, 1, 0, 1),
                PMPCheck(0x1100, 1, 0, 1),
                PMPCheck(0x11FF, 1, 0, 1),
                PMPCheck(0x1200, 0, 0, 0),
                PMPCheck(0x0FFF, 0, 0, 0),
            ],
            pmp_grain_log=pmp_grain_log,
        )

    def test_napot_expanded_by_grain(self):
        # pmpaddr=0x80, grain=4 forces bits [2:0]=1.
        # Effective pmpaddr=0x87, 3 trailing ones, 64B region [0x200, 0x240)
        self.run_pmp_test(
            [PMPEntry(addr=0x80, cfg=make_cfg(r=1, w=1, a=PMPAFlagEncoding.NAPOT))],
            [
                PMPCheck(0x200, 1, 1, 0),
                PMPCheck(0x220, 1, 1, 0),
                PMPCheck(0x23C, 1, 1, 0),
                PMPCheck(0x240, 0, 0, 0),
                PMPCheck(0x1FC, 0, 0, 0),
            ],
            pmp_grain_log=6,
        )

    def test_pmp_grain_icache_validation_error(self):
        with pytest.raises(ValueError):
            GenParams(configurations.test.replace(pmp_register_count=16, pmp_grain_log=2, icache_enable=True))

    @pytest.mark.parametrize("grain", [2, 3, 4])
    def test_pmpaddr_discovery(self, grain):
        gen_params = GenParams(
            configurations.test.replace(pmp_register_count=16, pmp_grain_log=grain + 2, icache_enable=False)
        )
        csr_instances = CSRInstances(gen_params)
        DependencyContext.get().add_dependency(CSRInstancesKey(), csr_instances)
        csr = csr_instances.m_mode
        pmpaddr0_read = TestbenchIO(AdapterTrans.create(csr.pmpaddrx[0]._fu_read))
        pmpaddr1_read = TestbenchIO(AdapterTrans.create(csr.pmpaddrx[1]._fu_read))
        pmpcfg0_write = TestbenchIO(AdapterTrans.create(csr.pmpxcfg[0].fu_write_filter.method))
        pmpcfg0_read = TestbenchIO(AdapterTrans.create(csr.pmpxcfg[0]._fu_read))
        pmpcfg1_write = TestbenchIO(AdapterTrans.create(csr.pmpxcfg[1].fu_write_filter.method))

        test_module = ModuleConnector(
            csr_instances=csr_instances,
            pmpaddr0_read=pmpaddr0_read,
            pmpaddr1_read=pmpaddr1_read,
            pmpcfg0_write=pmpcfg0_write,
            pmpcfg0_read=pmpcfg0_read,
            pmpcfg1_write=pmpcfg1_write,
        )

        all_ones = (1 << gen_params.isa.xlen) - 1

        async def test_off_mode_masks_low_bits(sim: TestbenchContext):
            # In OFF/TOR mode, bits [G-1:0] read as zeros
            expected = all_ones & ~((1 << grain) - 1)
            sim.set(csr.pmpaddrx[0].value, all_ones)
            await sim.tick()
            result = (await pmpaddr0_read.call(sim))["data"]
            assert result == expected, f"OFF mode, grain={grain}: expected 0x{expected:x}, got 0x{result:x}"

        async def test_napot_mode_forces_low_bits(sim: TestbenchContext):
            # In NAPOT mode, bits [G-2:0] read as ones
            if grain < 2:
                return
            napot_cfg = make_cfg(a=PMPAFlagEncoding.NAPOT)
            await pmpcfg0_write.call(sim, data=napot_cfg)
            sim.set(csr.pmpaddrx[0].value, 0)
            await sim.tick()
            expected = (1 << (grain - 1)) - 1
            result = (await pmpaddr0_read.call(sim))["data"]
            assert result == expected, f"NAPOT mode, grain={grain}: expected 0x{expected:x}, got 0x{result:x}"

        async def test_na4_filtered_to_off(sim: TestbenchContext):
            # When G >= 1, writing NA4 is OFF
            if grain < 1:
                return
            na4_cfg = make_cfg(r=1, w=1, x=1, a=PMPAFlagEncoding.NA4)
            expected = make_cfg(r=1, w=1, x=1, a=PMPAFlagEncoding.OFF)
            await pmpcfg0_write.call(sim, data=na4_cfg)
            await sim.tick()
            result = (await pmpcfg0_read.call(sim))["data"]
            assert result == expected, f"NA4→OFF filter, grain={grain}: expected 0x{expected:x}, got 0x{result:x}"

        async def test_mode_switch_changes_readback(sim: TestbenchContext):
            if grain < 2:
                return
            test_val = 0xABCD0000
            tor_mask = (1 << grain) - 1
            napot_mask = (1 << (grain - 1)) - 1

            # Reset cfg to OFF, write addr
            await pmpcfg0_write.call(sim, data=make_cfg(a=PMPAFlagEncoding.OFF))
            sim.set(csr.pmpaddrx[0].value, test_val)
            await sim.tick()
            result = (await pmpaddr0_read.call(sim))["data"]
            expected_off = test_val & ~tor_mask
            assert (
                result == expected_off
            ), f"mode switch OFF, grain={grain}: expected 0x{expected_off:x}, got 0x{result:x}"

            # Switch to NAPOT
            await pmpcfg0_write.call(sim, data=make_cfg(a=PMPAFlagEncoding.NAPOT))
            await sim.tick()
            result = (await pmpaddr0_read.call(sim))["data"]
            expected_napot = test_val | napot_mask
            assert (
                result == expected_napot
            ), f"mode switch NAPOT, grain={grain}: expected 0x{expected_napot:x}, got 0x{result:x}"

        async def test_per_entry_cfg_independence(sim: TestbenchContext):
            if grain < 2:
                return
            test_val = 0x12340000
            tor_mask = (1 << grain) - 1
            napot_mask = (1 << (grain - 1)) - 1

            # Entry 0: OFF, Entry 1: NAPOT
            await pmpcfg0_write.call(sim, data=make_cfg(a=PMPAFlagEncoding.OFF))
            await pmpcfg1_write.call(sim, data=make_cfg(a=PMPAFlagEncoding.NAPOT))
            sim.set(csr.pmpaddrx[0].value, test_val)
            sim.set(csr.pmpaddrx[1].value, test_val)
            await sim.tick()

            result0 = (await pmpaddr0_read.call(sim))["data"]
            expected0 = test_val & ~tor_mask
            assert result0 == expected0, f"entry 0 OFF, grain={grain}: expected 0x{expected0:x}, got 0x{result0:x}"

            result1 = (await pmpaddr1_read.call(sim))["data"]
            expected1 = test_val | napot_mask
            assert result1 == expected1, f"entry 1 NAPOT, grain={grain}: expected 0x{expected1:x}, got 0x{result1:x}"

        async def test_reserved_rw_combination(sim: TestbenchContext):
            # R=0, W=1 is reserved (WARL): must be filtered to R=0, W=0
            reserved_cfg = make_cfg(r=0, w=1, x=1, a=PMPAFlagEncoding.TOR)
            expected = make_cfg(r=0, w=0, x=1, a=PMPAFlagEncoding.TOR)
            await pmpcfg0_write.call(sim, data=reserved_cfg)
            await sim.tick()
            result = (await pmpcfg0_read.call(sim))["data"]
            assert result == expected, f"WARL R=0,W=1: expected 0x{expected:x}, got 0x{result:x}"

        async def test_l_bit_forced_zero(sim: TestbenchContext):
            # L bit is not implemented: writes should be forced to 0
            cfg_with_l = make_cfg(r=1, w=1, x=1, a=PMPAFlagEncoding.TOR, lock=1)
            expected = make_cfg(r=1, w=1, x=1, a=PMPAFlagEncoding.TOR, lock=0)
            await pmpcfg0_write.call(sim, data=cfg_with_l)
            await sim.tick()
            result = (await pmpcfg0_read.call(sim))["data"]
            assert result == expected, f"L bit forced 0: expected 0x{expected:x}, got 0x{result:x}"

        async def test_reserved_bits_forced_zero(sim: TestbenchContext):
            # Bits 5-6 (reserved) should always read as 0
            cfg_with_reserved = make_cfg(r=1, x=1, a=PMPAFlagEncoding.TOR) | (0b11 << 5)
            expected = make_cfg(r=1, x=1, a=PMPAFlagEncoding.TOR)
            await pmpcfg0_write.call(sim, data=cfg_with_reserved)
            await sim.tick()
            result = (await pmpcfg0_read.call(sim))["data"]
            assert result == expected, f"Reserved bits forced 0: expected 0x{expected:x}, got 0x{result:x}"

        async def process(sim: TestbenchContext):
            await test_off_mode_masks_low_bits(sim)
            await test_napot_mode_forces_low_bits(sim)
            await test_na4_filtered_to_off(sim)
            await test_reserved_rw_combination(sim)
            await test_l_bit_forced_zero(sim)
            await test_reserved_bits_forced_zero(sim)
            await test_mode_switch_changes_readback(sim)
            await test_per_entry_cfg_independence(sim)

        with self.run_simulation(test_module) as sim:
            sim.add_testbench(process)
