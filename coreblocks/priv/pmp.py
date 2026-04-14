from amaranth import *
from amaranth.lib import data
from amaranth_types import HasElaborate
from transactron.core import TModule
from transactron.utils import DependencyContext

from coreblocks.arch.isa_consts import PMPAFlagEncoding, PMPCfgLayout, PrivilegeLevel
from coreblocks.interface.keys import CSRInstancesKey
from coreblocks.params import *


class PMPLayout(data.StructLayout):
    def __init__(self):
        super().__init__({"r": 1, "w": 1, "x": 1})


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

    def __init__(self, gen_params: GenParams) -> None:
        self.gen_params = gen_params
        self.csr = DependencyContext.get().get_dependency(CSRInstancesKey()).m_mode
        self.addr = Signal(gen_params.isa.xlen)
        self.result = Signal(PMPLayout())

    def elaborate(self, platform) -> HasElaborate:
        m = TModule()

        grain = self.gen_params.pmp_grain
        n = self.gen_params.pmp_register_count

        if n == 0:
            m.d.comb += self.result.r.eq(1)
            m.d.comb += self.result.w.eq(1)
            m.d.comb += self.result.x.eq(1)
            return m

        priv_mode = self.csr.priv_mode.value
        with m.If(priv_mode == PrivilegeLevel.MACHINE):
            m.d.comb += self.result.r.eq(1)
            m.d.comb += self.result.w.eq(1)
            m.d.comb += self.result.x.eq(1)

        entry_matches = []
        cfgs = []
        addr_vals = []

        for i in range(n):
            cfg_val = data.View(PMPCfgLayout(), self.csr.pmpxcfg[i].value)
            addr_val = self.csr.pmpaddrx[i].value
            cfgs.append(cfg_val)
            addr_vals.append(addr_val)

            entry_match = Signal(name=f"match_{i}")

            with m.Switch(cfg_val.A):
                with m.Case(PMPAFlagEncoding.OFF):
                    m.d.comb += entry_match.eq(0)
                with m.Case(PMPAFlagEncoding.TOR):
                    lower = addr_vals[i - 1][grain:] if i > 0 else 0
                    m.d.comb += entry_match.eq(
                        (self.addr[2 + grain :] >= lower) & (self.addr[2 + grain :] < addr_val[grain:])
                    )
                with m.Case(PMPAFlagEncoding.NA4):
                    if grain == 0:
                        m.d.comb += entry_match.eq(self.addr[2:] == addr_val)
                    else:
                        m.d.comb += entry_match.eq(0)
                with m.Case(PMPAFlagEncoding.NAPOT):
                    start_bit = max(0, grain - 1)
                    napot_mask = addr_val[start_bit:] ^ (addr_val[start_bit:] + 1)
                    m.d.comb += entry_match.eq(
                        (self.addr[2 + start_bit :] & ~napot_mask) == (addr_val[start_bit:] & ~napot_mask)
                    )

            entry_matches.append(entry_match)

        matches = Cat(entry_matches)
        one_hot = matches & (~matches + 1)

        r_bits = Cat(cfg.R for cfg in cfgs)
        w_bits = Cat(cfg.W for cfg in cfgs)
        x_bits = Cat(cfg.X for cfg in cfgs)
        l_bits = Cat(cfg.L for cfg in cfgs)

        selected_r = (one_hot & r_bits).any()
        selected_w = (one_hot & w_bits).any()
        selected_x = (one_hot & x_bits).any()
        selected_l = (one_hot & l_bits).any()

        with m.If(matches.any() & ((priv_mode != PrivilegeLevel.MACHINE) | selected_l)):
            m.d.comb += self.result.r.eq(selected_r)
            m.d.comb += self.result.w.eq(selected_w)
            m.d.comb += self.result.x.eq(selected_x)

        return m
