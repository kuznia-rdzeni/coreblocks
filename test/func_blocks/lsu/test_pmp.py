from dataclasses import dataclass

from amaranth import *
from transactron.testing import TestCaseWithSimulator, TestbenchContext

from coreblocks.params import GenParams
from coreblocks.params.configurations import test_core_config
from coreblocks.arch.isa_consts import PMPAFlagEncoding, PrivilegeLevel
from coreblocks.priv.csr.csr_instances import MachineModeCSRRegisters
from coreblocks.func_blocks.fu.lsu.pmp import PMPChecker


def make_cfg(*, r=0, w=0, x=0, a=0, lock=0) -> int:
    return (lock << 7) | (a << 3) | (x << 2) | (w << 1) | r


@dataclass
class PMPEntry:
    addr: int
    cfg: int


@dataclass
class PMPCheck:
    addr: int
    r: int
    w: int
    x: int


class PMPTestCircuit(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.csr = MachineModeCSRRegisters(gen_params)
        self.pmp = PMPChecker(gen_params, self.csr.pmpaddrx, self.csr.pmpxcfg, self.csr.priv_mode)

    def elaborate(self, platform):
        m = Module()
        m.submodules.csr = self.csr
        m.submodules.pmp = self.pmp
        return m


class TestPMPDirect(TestCaseWithSimulator):
    def run_pmp_test(self, entries: list[PMPEntry], checks: list[PMPCheck], priv_mode=PrivilegeLevel.USER):
        gen_params = GenParams(test_core_config.replace(pmp_register_count=16))
        test_module = PMPTestCircuit(gen_params)

        async def process(sim: TestbenchContext):
            csr = test_module.csr
            sim.set(csr.priv_mode.value, priv_mode)
            for i, entry in enumerate(entries):
                sim.set(csr.pmpaddrx[i].value, entry.addr)
                sim.set(csr.pmpxcfg[i].value, entry.cfg)

            for c in checks:
                sim.set(test_module.pmp.addr, c.addr)
                result = sim.get(test_module.pmp.result)
                assert result.r == c.r, f"addr=0x{c.addr:08x}: expected r={c.r}, got {result.r}"
                assert result.w == c.w, f"addr=0x{c.addr:08x}: expected w={c.w}, got {result.w}"
                assert result.x == c.x, f"addr=0x{c.addr:08x}: expected x={c.x}, got {result.x}"

        with self.run_simulation(test_module) as sim:
            sim.add_testbench(process)

    def test_mmode_no_entries(self):
        self.run_pmp_test([], [PMPCheck(0x1000, 1, 1, 1), PMPCheck(0xDEAD, 1, 1, 1)], priv_mode=PrivilegeLevel.MACHINE)

    def test_umode_no_entries(self):
        self.run_pmp_test([], [PMPCheck(0x1000, 0, 0, 0), PMPCheck(0xDEAD, 0, 0, 0)])

    def test_priority(self):
        self.run_pmp_test(
            [
                PMPEntry(addr=0x2000 >> 2, cfg=make_cfg(r=1, a=PMPAFlagEncoding.TOR)),
                PMPEntry(addr=0x4000 >> 2, cfg=make_cfg(r=1, w=1, a=PMPAFlagEncoding.TOR)),
            ],
            [
                PMPCheck(0x1000, 1, 0, 0),
                PMPCheck(0x3000, 1, 1, 0),
            ],
        )

    def test_locked_mmode(self):
        self.run_pmp_test(
            [PMPEntry(addr=0x2000 >> 2, cfg=make_cfg(lock=1, a=PMPAFlagEncoding.TOR))],
            [PMPCheck(0x1000, 0, 0, 0)],
            priv_mode=PrivilegeLevel.MACHINE,
        )

    def test_unlocked_mmode(self):
        self.run_pmp_test(
            [PMPEntry(addr=0x2000 >> 2, cfg=make_cfg(a=PMPAFlagEncoding.TOR))],
            [PMPCheck(0x1000, 1, 1, 1)],
            priv_mode=PrivilegeLevel.MACHINE,
        )

    def test_tor_basic(self):
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
        )

    def test_tor_range(self):
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
        )

    def test_tor_no_perms(self):
        self.run_pmp_test(
            [PMPEntry(addr=0x2000 >> 2, cfg=make_cfg(a=PMPAFlagEncoding.TOR))],
            [PMPCheck(0x1000, 0, 0, 0)],
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

    def test_napot(self):
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
        )
