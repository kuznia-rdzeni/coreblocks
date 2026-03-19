from amaranth import *
from amaranth.lib import data
from amaranth_types import HasElaborate
from coreblocks.arch.isa_consts import PrivilegeLevel
from coreblocks.params import *
from transactron.core import TModule


class PMPLayout(data.StructLayout):
    def __init__(self):
        super().__init__({"r": unsigned(1), "w": unsigned(1), "x": unsigned(1)})


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

    def __init__(self, gen_params: GenParams, pmpaddrx: list, pmpxcfg: list, priv_mode) -> None:
        self.gen_params = gen_params
        self.pmpaddrx = pmpaddrx
        self.pmpxcfg = pmpxcfg
        self.priv_mode = priv_mode
        self.addr = Signal(gen_params.isa.xlen)

        self.result = Signal(PMPLayout())

    def elaborate(self, platform) -> HasElaborate:
        m = TModule()

        priv_mode = self.priv_mode.value
        with m.If(priv_mode == PrivilegeLevel.MACHINE):
            m.d.comb += self.result.r.eq(1)
            m.d.comb += self.result.w.eq(1)
            m.d.comb += self.result.x.eq(1)
        with m.Else():
            m.d.comb += self.result.r.eq(0)
            m.d.comb += self.result.w.eq(0)
            m.d.comb += self.result.x.eq(0)

        for i in reversed(range(self.gen_params.pmp_register_count)):
            cfg_val = self.pmpxcfg[i].value
            addr_val = self.pmpaddrx[i].value

            entry_match = Signal(name=f"match_{i}")

            a_bits = cfg_val[3:5]
            l_bit = cfg_val[7]

            with m.Switch(a_bits):
                with m.Case(0):  # OFF
                    m.d.comb += entry_match.eq(0)
                with m.Case(1):  # TOR
                    lower = self.pmpaddrx[i - 1].value if i > 0 else 0
                    m.d.comb += entry_match.eq((self.addr[2:] >= lower) & (self.addr[2:] < addr_val))
                with m.Case(2):  # NA4
                    m.d.comb += entry_match.eq(self.addr[2:] == addr_val)
                with m.Case(3):  # NAPOT
                    napot_mask = addr_val ^ (addr_val + 1)
                    m.d.comb += entry_match.eq((self.addr[2:] & ~napot_mask) == (addr_val & ~napot_mask))

            with m.If(entry_match & ((priv_mode != PrivilegeLevel.MACHINE) | l_bit)):
                m.d.comb += self.result.r.eq(cfg_val[0])
                m.d.comb += self.result.w.eq(cfg_val[1])
                m.d.comb += self.result.x.eq(cfg_val[2])

        return m
