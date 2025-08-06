from amaranth import *
from amaranth.lib import data
from coreblocks.interface.keys import CSRInstancesKey
from transactron.utils.dependencies import DependencyContext
from coreblocks.params import *
from transactron.utils import HasElaborate
from transactron.core import TModule, Transaction
from transactron.utils.amaranth_ext.coding import PriorityEncoder
from transactron.utils.amaranth_ext.functions import count_trailing_zeros
from coreblocks.arch.isa_consts import PMPAFlagEncoding
from transactron.lib.logging import HardwareLogger


class PMPLayout(data.StructLayout):
    def __init__(self):
        super().__init__({"x": unsigned(1), "w": unsigned(1), "r": unsigned(1)})


class PMPChecker(Elaboratable):
    """
    Implementation of physical memory protection checker. It may or may not be a part of LSU.
    This is a combinational circuit with return value read from `result` output.

    Attributes
    ----------
    addr : Signal
        Memory address, for which PMPs are requested.
    result : View
        PMPs for given address.
    """

    def __init__(self, gen_params: GenParams) -> None:
        self.result = Signal(PMPLayout())
        self.addr = Signal(gen_params.isa.xlen)
        self.log = HardwareLogger("backend.lsu.pmp")

    def elaborate(self, platform) -> HasElaborate:
        m = TModule()
        self.dependency_manager = DependencyContext.get()
        m_csr = self.dependency_manager.get_dependency(CSRInstancesKey()).m_mode

        with Transaction(name="PMP_CSR_read").body(m):
            pmpxcfg_val = Array(cfg.read(m).data for cfg in m_csr.pmpxcfg)
            pmpaddrx_val = Array(addr.read(m).data for addr in m_csr.pmpaddrx)
            matchings = Array(Signal() for _ in pmpxcfg_val)
            for i, (cfg, addr) in enumerate(zip(pmpxcfg_val, pmpaddrx_val)):
                a_flag = (cfg & 0b11000) >> 3
                with m.Switch(a_flag):
                    with m.Case(PMPAFlagEncoding.OFF):
                        m.d.comb += matchings[i].eq(0)
                    with m.Case(PMPAFlagEncoding.TOR):
                        # A=1 - Top of range - from value of previous address to this address
                        start = pmpaddrx_val[i - 1] if i > 0 else 0
                        end = addr
                        with m.If((self.addr >= start) & (self.addr < end)):
                            m.d.comb += matchings[i].eq(1)
                    with m.Case(PMPAFlagEncoding.NA4):
                        # A=2 - NA4 - 4-byte region
                        with m.If(self.addr >> 2 == addr):
                            m.d.comb += matchings[i].eq(1)
                    with m.Case(PMPAFlagEncoding.NAPOT):
                        # A=3 - NAPOT - 2^(3 + position of first zero from right) region
                        fzero = count_trailing_zeros(~addr)
                        size = 1 << (fzero + 3)
                        start = addr - (fzero - 1)
                        end = start + size
                        with m.If((self.addr >= start) & (self.addr < end)):
                            m.d.comb += matchings[i].eq(1)
            m.submodules.enc_select = enc_select = PriorityEncoder(width=len(pmpxcfg_val))
            select_vector = Cat(matchings)
            m.d.comb += enc_select.i.eq(select_vector)
            with m.If(enc_select.n):
                m.d.sync += self.result.eq(0)
                with m.If(self.addr != 0):
                    self.log.debug(
                        m, 1, "PMP check addr=0x{:08x} NOT MATCHED", self.addr, pmpaddrx_val[0], pmpxcfg_val[0]
                    )
            with m.Else():
                m.d.sync += self.result.eq(pmpxcfg_val[enc_select.o])
                with m.If(self.addr != 0):
                    self.log.debug(
                        m, 1, "PMP check addr=0x{:08x} result={}", self.addr, pmpxcfg_val[enc_select.o] & 0b111
                    )

        return m
