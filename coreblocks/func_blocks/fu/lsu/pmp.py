from functools import reduce
from operator import or_
from amaranth import *
from amaranth.lib import data
from coreblocks.interface.keys import CSRInstancesKey
from transactron.utils.dependencies import DependencyContext
from coreblocks.params import *
from transactron.utils import HasElaborate
from transactron.core import TModule, Transaction


class PMPLayout(data.StructLayout):
    def __init__(self):
        super().__init__({"xwr": unsigned(3)})


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

    def elaborate(self, platform) -> HasElaborate:
        m = TModule()
        self.dependency_manager = DependencyContext.get()
        m_csr = self.dependency_manager.get_dependency(CSRInstancesKey()).m_mode
        # Możliwe że w niektórych testach to jest niedostępne?
        # Trzeba dodać w samych testach CSRInstancesKey!!!

        with Transaction(name="PMP CSR read").body(m):
            pmpxcfg_val = [cfg.read(m).data for cfg in m_csr.pmpxcfg]
            pmpaddrx_val = [addr.read(m).data for addr in m_csr.pmpaddrx]
            outputs = [Signal(PMPLayout()) for _ in pmpxcfg_val]
            for i, (cfg, addr) in enumerate(zip(pmpxcfg_val, pmpaddrx_val)):
                a_flag = (cfg & 0b11000) >> 3
                matching = False
                with m.If(a_flag == 1):
                    # A=1 - Top of range - od wartości poprzedniego do tego adr
                    start = pmpaddrx_val[i - 1] if i > 0 else 0
                    end = addr
                    with m.If((self.addr >= start) & (self.addr <= end)):
                        matching = True
                with m.Elif(a_flag == 2):
                    # A=2 - NA4 - region 4 bajtowy
                    with m.If(self.addr == addr):
                        matching = True
                with m.Elif(a_flag == 3):
                    # A=3 - NAPOT - region 8*2^(tyle na jakiej pozycji jest pierwsze zero od prawej)
                    # TODO
                    pass
                with m.If(matching):
                    m.d.comb += outputs[i].eq(cfg & 111)
            # TODO: Ma wchodzić tylko jeden region i koniec dalej nie sprawdzamy
            # Jak to zrobić??
            m.d.comb += self.result.eq(reduce(or_, [Value.cast(o) for o in outputs], 0))
        return m
