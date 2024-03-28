from amaranth import *
from coreblocks.frontend.decoder.isa import PrivilegeLevel
from coreblocks.priv.csr.csr_register import CSRRegister
from transactron.core.transaction import Transaction
from transactron.utils.dependencies import DependencyManager
from coreblocks.params.genparams import GenParams
from coreblocks.interface.keys import AsyncInterruptInsertSignalKey, MretKey

from transactron.core import Method, TModule, def_method

### TODO: upgrade to component
class InternalInterruptController(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params
        dm = gen_params.get(DependencyManager)
       
        self.mstatus_mie = CSRRegister(None, gen_params, width=1) # MIE bit - global interrupt enable - part of mstatus CSR
        self.mstatus_mpie = CSRRegister(None, gen_params, width=1) # MPIE bit - previous MIE - part of mstatus
        self.mstatus_mpp = CSRRegister(None, gen_params, width=2, ro_bits=0b11, reset=PrivilegeLevel.MACHINE) # MPP bit - previous priv mode - part of mstatus
        # TODO: filter xpp for only legal modes (when not read-only)

        # TODO NOW: SPP must be read only 0
        # TODO NOW: set fu/priority
        # TODO: NMI

        self.mie = CSRRegister(69, gen_params) # set to read only
        self.mip = CSRRegister(70, gen_params)

        self.interrupt_insert = Signal()
        dm.add_dependency(AsyncInterruptInsertSignalKey(), self.interrupt_insert)
        
        # export only bits mxlen-1:16
        self.edge_report_interrupt = Signal()
        self.level_report_interrupt = Signal()
        self.edge_reported_mask = 0
        self.non_maskable_interrupt = Signal() # in standard riscv it is not recoverable

        ## wait registers have specific
        ## lower part is read only and needs direct access in mip
        ## report only for custom
        ## no - direct singals -> this is external interface
        ## it should be parametrized if clearable or direct

        ## TODO: priority + mcause + vector (
        ## MAYBE LATCHING? WHEN TO REPORT CAUSE??
        ## latch on laszt interrupt insert
        ## o co jak zniknie od czasu reportu w fu do retirementu

        self.mret = Method()
        dm.add_dependency(MretKey(), self.mret)

        self.entry = Method()

    def elaborate(self, platform):
        m = TModule()

        m.submodules += [self.mstatus_mie, self.mstatus_mpie, self.mstatus_mpp, self.mie]

        interrupt_enable = self.mstatus_mie.read(m).data
        interrupt_pending = (self.mie.read(m).data & self.mip.read(m).data).any()
        m.d.comb += self.interrupt_insert.eq(interrupt_pending & interrupt_enable)

        with Transaction().body(m):
            # ok, treat sequence as 1.csr read modify write 2. apply new edge interrupts. (not standarized by spec)
            # so edge interrupts are not missed and can be catched between read and clear instructions

            edge_disabled = self.mip.read(m).data & ~self.mip.read_comb(m).data & self.edge_reported_mask
            value = self.mip.read(m).data & self.edge_reported_mask
            value |= self.level_report_interrupt | self.edge_reported_mask
            # because of ro_bits set in CSR, level reported interrupts are not ignored with writes
            
            # or should read_comb be used???
            # ok needs to be -> what if cleared and reported at the same time but other is not?
            self.mip.write(m, value)

            

        @def_method(m, self.mret)
        def _():
            self.mstatus_mie.write(m, self.mstatus_mpie.read(m).data)
            self.mstatus_mpie.write(m, 1)
            # TODO: Set mpp when other privilege modes are implemented

        # TODO NOW: mret / entry conflict priority emm how?? 

        @def_method(m, self.entry)
        def _():
            self.mstatus_mie.write(m, 0)
            self.mstatus_mpie.write(m, self.mie.read(m).data)

        return m
