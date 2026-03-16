from amaranth import *
from amaranth.lib import data
from amaranth_types import HasElaborate
from coreblocks.arch.isa_consts import PrivilegeLevel
from coreblocks.params import *
from transactron.core import TModule
from transactron.utils import DependencyContext
from coreblocks.interface.keys import CSRInstancesKey


class PMPLayout(data.StructLayout):
    def __init__(self):
        super().__init__({"r": unsigned(1), "w": unsigned(1), "x": unsigned(1)})


class PMPChecker(Elaboratable):
    """
    Implementation of physical memory protection checker.
    This is a combinational circuit with return value read from `result` output.

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
        self.addr = Signal(gen_params.isa.xlen)
        self.dm = DependencyContext.get()

        self.result = Signal(PMPLayout())

    def elaborate(self, platform) -> HasElaborate:
        m = TModule()

        csr = self.dm.get_dependency(CSRInstancesKey())

        priv_mode = csr.m_mode.priv_mode.value
        with m.If(priv_mode == PrivilegeLevel.MACHINE):
            m.d.comb += self.result.r.eq(1)
            m.d.comb += self.result.w.eq(1)
            m.d.comb += self.result.x.eq(1)
        with m.Else():
            m.d.comb += self.result.r.eq(0)
            m.d.comb += self.result.w.eq(0)
            m.d.comb += self.result.x.eq(0)

        for i in reversed(range(self.gen_params.pmp_register_count)):
            cfg_val = csr.m_mode.pmpxcfg[i].value
            addr_val = csr.m_mode.pmpaddrx[i].value
            addr_val

            entry_match = Signal(name=f"match_{i}")

            a_bits = cfg_val[3:5]
            l_bit = cfg_val[7]

            with m.Switch(a_bits):
                with m.Case(0):  # OFF
                    m.d.comb += entry_match.eq(0)
                with m.Case(1):  # TOR
                    pass
                with m.Case(2):  # NA4
                    pass
                with m.Case(3):  # NAPOT
                    pass

            with m.If(entry_match & ((priv_mode != PrivilegeLevel.MACHINE) | l_bit)):
                m.d.comb += self.result.r.eq(cfg_val[0])
                m.d.comb += self.result.w.eq(cfg_val[1])
                m.d.comb += self.result.x.eq(cfg_val[2])

        return m
