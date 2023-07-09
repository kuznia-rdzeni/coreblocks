from amaranth import *
from amaranth.lib.enum import IntEnum

from typing import Optional

from coreblocks.params.genparams import GenParams
from coreblocks.structs_common.csr import CSRRegister
from transactron.core import Method, Transaction, def_method, TModule


class CSRAddress(IntEnum, shape=12):
    MTVEC = 0x305
    MCAUSE = 0x342
    MEPC = 0x341
    CYCLE = 0xC00
    TIME = 0xC01
    INSTRET = 0xC02
    CYCLEH = 0xC80
    TIMEH = 0xC81
    INSTRETH = 0xC82


class DoubleCounterCSR(Elaboratable):
    """DoubleCounterCSR
    Groups two `CSRRegisters` to form counter with double `isa.xlen` width.

    Attributes
    ----------
    increment: Method
        Increments the counter by 1. At overflow, counter value is set to 0.
    """

    def __init__(self, gen_params: GenParams, low_addr: CSRAddress, high_addr: Optional[CSRAddress] = None):
        """
        Parameters
        ----------
        gen_params: GenParams
            Core generation parameters.
        low_addr: CSRAddress
            Address of the CSR register representing lower part of the counter (bits `[isa.xlen-1 : 0]`).
        high_addr: CSRAddress or None, optional
            Address of the CSR register representing higher part of the counter (bits `[2*isa.xlen-1 : isa.xlen]`).
            If high_addr is None or not provided, then higher CSR is not synthetised and only the width of
            low_addr CSR is available to the counter.
        """
        self.gen_params = gen_params

        self.increment = Method()

        self.register_low = CSRRegister(low_addr, gen_params)
        self.register_high = CSRRegister(high_addr, gen_params) if high_addr is not None else None

    def elaborate(self, platform):
        m = TModule()

        m.submodules.register_low = self.register_low
        if self.register_high is not None:
            m.submodules.register_high = self.register_high

        @def_method(m, self.increment)
        def _():
            register_read = self.register_low.read(m).data
            self.register_low.write(m, data=register_read + 1)

            if self.register_high is not None:
                with m.If(register_read == (1 << self.gen_params.isa.xlen) - 1):
                    self.register_high.write(m, data=self.register_high.read(m).data + 1)

        return m


class GenericCSRRegisters(Elaboratable):
    def __init__(self, gp: GenParams):
        self.csr_cycle = DoubleCounterCSR(gp, CSRAddress.CYCLE, CSRAddress.CYCLEH)
        # TODO: CYCLE should be alias to TIME
        self.csr_time = DoubleCounterCSR(gp, CSRAddress.TIME, CSRAddress.TIMEH)

        self.mcause = CSRRegister(CSRAddress.MCAUSE, gp)

    def elaborate(self, platform):
        m = TModule()

        m.submodules.csr_cycle = self.csr_cycle
        m.submodules.csr_time = self.csr_time
        m.submodules.mcause = self.mcause

        with Transaction().body(m):
            self.csr_cycle.increment(m)
            self.csr_time.increment(m)

        return m
