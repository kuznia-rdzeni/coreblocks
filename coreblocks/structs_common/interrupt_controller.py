from amaranth import *
from coreblocks.params.dependencies import DependencyManager
from coreblocks.params.genparams import GenParams
from coreblocks.params.keys import AsyncInterruptInsertSignalKey
from coreblocks.structs_common.csr import CSRRegister
from coreblocks.structs_common.csr_generic import CSRAddress

from transactron.core import Method, TModule, Transaction, def_method

# TODO: Public enum
_MEI_BIT = 11  # Machine-level external interrupt
_MTI_BIT = 7  # Machine timer interrupt
_MSI_BIT = 3  # Machine-level software interrupts


class InterruptController(Elaboratable):
    def __init__(self, gp: GenParams):
        # TODO: NMI
        # TODO: Support setting mip by CSR and add CSR (and somehow MRET?) as second interrupt entry point (should be processed immediately by spec)
        # TODO: Custom interrupts 31-16

        self.gp = gp

        self.interrupt_insert = Signal()
        gp.get(DependencyManager).add_dependency(AsyncInterruptInsertSignalKey(), self.interrupt_insert)

        self.report_interrupt = [Method() for _ in range(gp.isa.xlen)]

        # From standard interrupts (bits[15:0]) only those from supported mode are enabled
        self.mie_mask = (1 << _MEI_BIT) | (1 << _MTI_BIT) | (1 << _MSI_BIT)
        self.mie = CSRRegister(CSRAddress.MIE, gp, ro_bits=~self.mie_mask)
        # From supported standard interrupts, all are read-only in mip and must be cleared by external
        # hardware that raised them (PIC, timer, CSR) (from SPEC).
        self.mip = CSRRegister(CSRAddress.MIP, gp, ro_bits=-1)

        self.cause = Signal(gp.isa.xlen_log)

    def elaborate(self, platform):
        m = TModule()

        interrupt_pending = Signal()

        m.d.comb += self.interrupt_insert.eq(interrupt_pending)

        mip_update = Signal(self.gp.isa.xlen)
        # Only support interrupts that can be enabled
        for interrupt_number in range(self.gp.isa.xlen):
            if self.mie_mask & (1 << interrupt_number):

                @def_method(m, self.report_interrupt[interrupt_number])
                def _():
                    # m.d.sync += self.cause.eq(interrupt_number) # Nooooo what if enabled only by mie?
                    m.d.comb += mip_update[interrupt_number].eq(1)

        with Transaction.body(m):
            self.mip.write(m, self.mip.read(m) | mip_update)  # TODO: What if written at the same time?

        return m
