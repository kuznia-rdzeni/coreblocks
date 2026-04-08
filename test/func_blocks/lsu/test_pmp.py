from dataclasses import dataclass

import pytest

from coreblocks.arch.isa_consts import PMPAFlagEncoding, PrivilegeLevel
from coreblocks.priv.pmp import PMPCfgLayout, PMPChecker
from coreblocks.params import GenParams
from coreblocks.params.configurations import test_core_config
from coreblocks.priv.csr.csr_instances import MachineModeCSRRegisters
from transactron.testing import TestbenchContext, TestCaseWithSimulator
from transactron.utils.amaranth_ext.elaboratables import ModuleConnector


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
    def run_pmp_test(
        self,
        entries: list[PMPEntry],
        checks: list[PMPCheck],
        priv_mode=PrivilegeLevel.USER,
        pmp_grain=0,
        icache_enable=False,
    ):
        gen_params = GenParams(
            test_core_config.replace(pmp_register_count=16, pmp_grain=pmp_grain, icache_enable=icache_enable)
        )
        csr = MachineModeCSRRegisters(gen_params)
        pmp = PMPChecker(gen_params, csr)
        test_module = ModuleConnector(csr=csr, pmp=pmp)

        async def process(sim: TestbenchContext):
            sim.set(csr.priv_mode.value, priv_mode)
            for i, entry in enumerate(entries):
                sim.set(csr.pmpaddrx[i].value, entry.addr)
                sim.set(csr.pmpxcfg[i].value, entry.cfg)

            for c in checks:
                sim.set(pmp.addr, c.addr)
                result = sim.get(pmp.result)
                assert result.r == c.r, f"addr=0x{c.addr:08x}: expected r={c.r}, got {result.r}"
                assert result.w == c.w, f"addr=0x{c.addr:08x}: expected w={c.w}, got {result.w}"
                assert result.x == c.x, f"addr=0x{c.addr:08x}: expected x={c.x}, got {result.x}"

        with self.run_simulation(test_module) as sim:
            sim.add_testbench(process)

    @pytest.mark.parametrize("pmp_grain", [0, 2, 4])
    def test_mmode_no_entries(self, pmp_grain):
        self.run_pmp_test(
            [],
            [PMPCheck(0x1000, 1, 1, 1), PMPCheck(0xDEAD, 1, 1, 1)],
            priv_mode=PrivilegeLevel.MACHINE,
            pmp_grain=pmp_grain,
        )

    @pytest.mark.parametrize("pmp_grain", [0, 2, 4])
    def test_umode_no_entries(self, pmp_grain):
        self.run_pmp_test([], [PMPCheck(0x1000, 0, 0, 0), PMPCheck(0xDEAD, 0, 0, 0)], pmp_grain=pmp_grain)

    @pytest.mark.parametrize("pmp_grain", [0, 2, 4])
    def test_priority(self, pmp_grain):
        self.run_pmp_test(
            [
                PMPEntry(addr=0x2000 >> 2, cfg=make_cfg(r=1, a=PMPAFlagEncoding.TOR)),
                PMPEntry(addr=0x4000 >> 2, cfg=make_cfg(r=1, w=1, a=PMPAFlagEncoding.TOR)),
            ],
            [
                PMPCheck(0x1000, 1, 0, 0),
                PMPCheck(0x3000, 1, 1, 0),
            ],
            pmp_grain=pmp_grain,
        )

    @pytest.mark.parametrize("pmp_grain", [0, 2, 4])
    def test_locked_mmode(self, pmp_grain):
        self.run_pmp_test(
            [PMPEntry(addr=0x2000 >> 2, cfg=make_cfg(lock=1, a=PMPAFlagEncoding.TOR))],
            [PMPCheck(0x1000, 0, 0, 0)],
            priv_mode=PrivilegeLevel.MACHINE,
            pmp_grain=pmp_grain,
        )

    @pytest.mark.parametrize("pmp_grain", [0, 2, 4])
    def test_unlocked_mmode(self, pmp_grain):
        self.run_pmp_test(
            [PMPEntry(addr=0x2000 >> 2, cfg=make_cfg(a=PMPAFlagEncoding.TOR))],
            [PMPCheck(0x1000, 1, 1, 1)],
            priv_mode=PrivilegeLevel.MACHINE,
            pmp_grain=pmp_grain,
        )

    @pytest.mark.parametrize("pmp_grain", [0, 2, 4])
    def test_tor_basic(self, pmp_grain):
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
            pmp_grain=pmp_grain,
        )

    @pytest.mark.parametrize("pmp_grain", [0, 2, 4])
    def test_tor_range(self, pmp_grain):
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
            pmp_grain=pmp_grain,
        )

    @pytest.mark.parametrize("pmp_grain", [0, 2, 4])
    def test_tor_no_perms(self, pmp_grain):
        self.run_pmp_test(
            [PMPEntry(addr=0x2000 >> 2, cfg=make_cfg(a=PMPAFlagEncoding.TOR))],
            [PMPCheck(0x1000, 0, 0, 0)],
            pmp_grain=pmp_grain,
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
            pmp_grain=4,
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

    @pytest.mark.parametrize("pmp_grain", [1, 2, 4])
    def test_na4_disabled_with_grain(self, pmp_grain):
        # NA4 is treated as OFF when grain > 0
        self.run_pmp_test(
            [PMPEntry(addr=0x1000 >> 2, cfg=make_cfg(r=1, w=1, a=PMPAFlagEncoding.NA4))],
            [PMPCheck(0x1000, 0, 0, 0), PMPCheck(0x1001, 0, 0, 0)],
            pmp_grain=pmp_grain,
        )

    @pytest.mark.parametrize("pmp_grain", [0, 2, 4])
    def test_napot(self, pmp_grain):
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
            pmp_grain=pmp_grain,
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
            pmp_grain=4,
        )

    def test_pmp_grain_icache_validation_error(self):
        with pytest.raises(ValueError):
            GenParams(test_core_config.replace(pmp_register_count=16, pmp_grain=0, icache_enable=True))
