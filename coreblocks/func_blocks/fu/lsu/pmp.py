from amaranth import *
from amaranth.lib import data
from amaranth_types import HasElaborate
from transactron.core import TModule

from coreblocks.arch.isa_consts import PMPAFlagEncoding, PrivilegeLevel
from coreblocks.params import *
from coreblocks.priv.csr.csr_instances import MachineModeCSRRegisters


class PMPLayout(data.StructLayout):
    def __init__(self):
        super().__init__({"r": 1, "w": 1, "x": 1})


class PMPCfgLayout(data.StructLayout):
    def __init__(self):
        super().__init__({"R": 1, "W": 1, "X": 1, "A": 2, "reserved": 2, "L": 1})


class PMPChecker(Elaboratable):
    """
    Implementation of physical memory protection checker.
    This is a combinational circuit with return value read from `result` output.

    M-mode accesses bypass PMP by default (result = 1/1/1) unless a matching
    locked entry (L=1) is found. S/U-mode accesses default to no access (0/0/0)
    if no entry matches.

    Attributes
    ----------
    addr : Signal
        Memory address, for which PMP checks are requested.
    result : PMPLayout
        RWX permission bits for the given address based on current PMP configuration
        and privilege mode. Bits are set to 0 if access is denied.
    """

    def __init__(self, gen_params: GenParams, csr: MachineModeCSRRegisters) -> None:
        self.gen_params = gen_params
        self.csr = csr
        self.addr = Signal(gen_params.isa.xlen)

        self.result = Signal(PMPLayout())

    def elaborate(self, platform) -> HasElaborate:
        m = TModule()

        priv_mode = self.csr.priv_mode.value
        with m.If(priv_mode == PrivilegeLevel.MACHINE):
            m.d.comb += self.result.r.eq(1)
            m.d.comb += self.result.w.eq(1)
            m.d.comb += self.result.x.eq(1)

        n = self.gen_params.pmp_register_count
        if n == 0:
            return m

        for i in reversed(range(n)):
            cfg_val = data.View(PMPCfgLayout(), self.csr.pmpxcfg[i].value)
            addr_val = self.csr.pmpaddrx[i].value

            entry_match = Signal(name=f"match_{i}")

            with m.Switch(cfg_val.A):
                with m.Case(PMPAFlagEncoding.OFF):
                    m.d.comb += entry_match.eq(0)
                with m.Case(PMPAFlagEncoding.TOR):
                    lower = self.csr.pmpaddrx[i - 1].value if i > 0 else 0
                    m.d.comb += entry_match.eq((self.addr[2:] >= lower) & (self.addr[2:] < addr_val))
                with m.Case(PMPAFlagEncoding.NA4):
                    m.d.comb += entry_match.eq(self.addr[2:] == addr_val)
                with m.Case(PMPAFlagEncoding.NAPOT):
                    napot_mask = addr_val ^ (addr_val + 1)
                    m.d.comb += entry_match.eq((self.addr[2:] & ~napot_mask) == (addr_val & ~napot_mask))

            with m.If(entry_match & ((priv_mode != PrivilegeLevel.MACHINE) | cfg_val.L)):
                m.d.comb += self.result.r.eq(cfg_val.R)
                m.d.comb += self.result.w.eq(cfg_val.W)
                m.d.comb += self.result.x.eq(cfg_val.X)

        return m
