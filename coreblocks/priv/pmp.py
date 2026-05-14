from amaranth import *
from amaranth.lib import data
from amaranth.lib.enum import Enum, auto, unique
from amaranth_types import HasElaborate
from transactron.core import TModule
from transactron.utils import DependencyContext, assign

from coreblocks.arch.isa_consts import PMPAFlagEncoding, PMPCfgLayout, PrivilegeLevel
from coreblocks.interface.keys import CSRInstancesKey
from coreblocks.params import *


class PMPLayout(data.StructLayout):
    def __init__(self):
        super().__init__({"r": 1, "w": 1, "x": 1})


@unique
class PMPOperationMode(Enum):
    LSU = auto()
    INSTRUCTION_FETCH = auto()
    MMU = auto()


class PMPChecker(Elaboratable):
    """
    Implementation of physical memory protection checker.
    This is a combinational circuit with return value read from `result` output.

    Effective mode depends on `mode`:
    - LSU: MPRV-aware (using MPP when MPRV=1 and current mode is M)
    - INSTRUCTION_FETCH: uses only current privilege mode
    - MMU: always behaves as supervisor mode

    In machine mode, accesses bypass PMP by default (result = 1/1/1) unless a
    matching locked entry (L=1) is found. S/U-mode accesses default to no
    access (0/0/0) if no entry matches.

    Attributes
    ----------
    paddr : Signal
        Memory address, for which PMP checks are requested.
    result : PMPLayout
        RWX permission bits for the given address based on current PMP configuration
        and privilege mode. Bits are set to 0 if access is denied.
    """

    def __init__(self, gen_params: GenParams, *, mode: PMPOperationMode) -> None:
        self.gen_params = gen_params
        self.mode = mode
        self.csr = DependencyContext.get().get_dependency(CSRInstancesKey()).m_mode
        self.paddr = Signal(gen_params.phys_addr_bits)
        self.result = Signal(PMPLayout())

    def elaborate(self, platform) -> HasElaborate:
        m = TModule()

        grain = self.gen_params.pmp_grain
        n = self.gen_params.pmp_register_count

        if n == 0:
            m.d.comb += self.result.eq(PMPLayout().const({"r": 1, "w": 1, "x": 1}))
            return m

        priv_mode = self.csr.priv_mode.value
        mprv = self.csr.mstatus_mprv.value
        mpp = self.csr.mstatus_mpp.value

        effective_priv_mode = Signal(PrivilegeLevel)
        match self.mode:
            case PMPOperationMode.LSU:
                m.d.comb += effective_priv_mode.eq(Mux(mprv, mpp, priv_mode))
            case PMPOperationMode.INSTRUCTION_FETCH:
                m.d.comb += effective_priv_mode.eq(priv_mode)
            case PMPOperationMode.MMU:
                m.d.comb += effective_priv_mode.eq(PrivilegeLevel.SUPERVISOR)

        with m.If(effective_priv_mode == PrivilegeLevel.MACHINE):
            m.d.comb += self.result.eq(PMPLayout().const({"r": 1, "w": 1, "x": 1}))

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
                        (self.paddr[2 + grain :] >= lower) & (self.paddr[2 + grain :] < addr_val[grain:])
                    )
                with m.Case(PMPAFlagEncoding.NA4):
                    if grain == 0:
                        m.d.comb += entry_match.eq(self.paddr[2:] == addr_val)
                    else:
                        m.d.comb += entry_match.eq(0)
                with m.Case(PMPAFlagEncoding.NAPOT):
                    # NAPOT region size is encoded by trailing ones in pmpaddr.
                    # XOR with (pmpaddr + 1) extracts those trailing ones as a mask.
                    # Bits below the mask define the region; bits above must match.
                    # With grain > 0, lower bits are forced to 1 so we skip them.
                    start_bit = max(0, grain - 1)
                    napot_mask = addr_val[start_bit:] ^ (addr_val[start_bit:] + 1)
                    m.d.comb += entry_match.eq(
                        (self.paddr[2 + start_bit :] & ~napot_mask) == (addr_val[start_bit:] & ~napot_mask)
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

        with m.If(matches.any() & ((effective_priv_mode != PrivilegeLevel.MACHINE) | selected_l)):
            m.d.comb += assign(self.result, {"r": selected_r, "w": selected_w, "x": selected_x})

        return m
