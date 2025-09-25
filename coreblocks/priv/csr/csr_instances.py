from amaranth import *
from coreblocks.arch import CSRAddress
from coreblocks.arch.csr_address import MstatusFieldOffsets
from coreblocks.arch.isa import Extension
from coreblocks.arch.isa_consts import PrivilegeLevel, XlenEncoding, TrapVectorMode
from coreblocks.socks.clint import ClintMtimeKey
from coreblocks.params.genparams import GenParams
from coreblocks.priv.csr.csr_register import CSRRegister
from coreblocks.priv.csr.aliased import AliasedCSR
from typing import Optional
from transactron.core import Method, Transaction, def_method, TModule
from transactron.utils import DependencyContext

PMPXCFG_WIDTH = 8


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


class MachineModeCSRRegisters(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.mvendorid = CSRRegister(CSRAddress.MVENDORID, gen_params, init=0)
        self.marchid = CSRRegister(CSRAddress.MARCHID, gen_params, init=gen_params.marchid)
        self.mimpid = CSRRegister(CSRAddress.MIMPID, gen_params, init=gen_params.mimpid)
        self.mhartid = CSRRegister(CSRAddress.MHARTID, gen_params, init=0)
        self.mscratch = CSRRegister(CSRAddress.MSCRATCH, gen_params)
        self.mconfigptr = CSRRegister(CSRAddress.MCONFIGPTR, gen_params, init=0)

        self.mstatus = AliasedCSR(CSRAddress.MSTATUS, gen_params)
        if gen_params.isa.xlen == 32:
            self.mstatush = AliasedCSR(CSRAddress.MSTATUSH, gen_params)

        self.mcause = CSRRegister(CSRAddress.MCAUSE, gen_params)

        self.mtvec = AliasedCSR(CSRAddress.MTVEC, gen_params)

        mepc_ro_bits = 0b1 if Extension.C in gen_params.isa.extensions else 0b11  # pc alignment (SPEC)
        self.mepc = CSRRegister(CSRAddress.MEPC, gen_params, ro_bits=mepc_ro_bits)

        self.mtval = CSRRegister(CSRAddress.MTVAL, gen_params)

        self.misa = CSRRegister(
            CSRAddress.MISA, gen_params, init=self._misa_value(gen_params), ro_bits=(1 << gen_params.isa.xlen) - 1
        )

        self.mcycle = DoubleCounterCSR(gen_params, CSRAddress.MCYCLE, CSRAddress.MCYCLEH)
        self.cycle = DoubleCounterCSR(
            gen_params, CSRAddress.CYCLE, CSRAddress.CYCLEH
        )  # FIXME: this should be a R/O shadow of mcycle

        self.pmpxcfg = []
        pmpcfg_subregisters = gen_params.isa.xlen // PMPXCFG_WIDTH
        pmpcfgx_cnt = gen_params.pmp_register_count // pmpcfg_subregisters
        for i in range(0, pmpcfgx_cnt):
            # In RV64, odd-numbered configuration registers pmpcfg1, ... pmpcfg15 are illegal.
            pmpcfg_index = i * 2 if gen_params.isa.xlen == 64 else i
            pmpcfg = AliasedCSR(getattr(CSRAddress, f"PMPCFG{pmpcfg_index}"), gen_params)

            # pmpcfgX CSR contains a range of pmpYcfg, pmpY+1cfg, ... fields that correspond to pmpaddrY entries
            for j in range(pmpcfg_subregisters):
                pmpcfg_sub = CSRRegister(None, gen_params, width=PMPXCFG_WIDTH)
                pmpcfg.add_field(j * PMPXCFG_WIDTH, pmpcfg_sub)
                self.pmpxcfg.append(pmpcfg_sub)
                setattr(self, f"pmp{i*pmpcfg_subregisters+j}cfg", pmpcfg_sub)

            setattr(self, f"pmpcfg{i}", pmpcfg)

        self.pmpaddrx = []
        for i in range(gen_params.pmp_register_count):
            reg = CSRRegister(getattr(CSRAddress, f"PMPADDR{i}"), gen_params)
            self.pmpaddrx.append(reg)
            setattr(self, f"pmpaddr{i}", reg)

        self.priv_mode = CSRRegister(
            None,
            gen_params,
            width=PrivilegeLevel.as_shape().width,
            init=PrivilegeLevel.MACHINE,
        )
        if gen_params._generate_test_hardware:
            self.priv_mode_public = AliasedCSR(CSRAddress.COREBLOCKS_TEST_PRIV_MODE, gen_params)
            self.priv_mode_public.add_field(0, self.priv_mode)

        self._mstatus_fields_implementation(gen_params, self.mstatus, self.mstatush)
        self._mtvec_fields_implementation(gen_params, self.mtvec)

    def elaborate(self, platform):
        m = TModule()

        for name, value in vars(self).items():
            if isinstance(value, CSRRegister) or isinstance(value, DoubleCounterCSR):
                m.submodules[name] = value

        with Transaction().body(m):
            self.mcycle.increment(m)
            self.cycle.increment(m)

        return m

    def _mtvec_fields_implementation(self, gen_params: GenParams, mtvec: AliasedCSR):
        def filter_legal_mode(m: TModule, v: Value):
            legal = Signal(1)
            m.d.av_comb += legal.eq((v == TrapVectorMode.DIRECT) | (v == TrapVectorMode.VECTORED))
            return (legal, v)

        self.mtvec_base = CSRRegister(None, gen_params, width=gen_params.isa.xlen - 2)
        mtvec.add_field(TrapVectorMode.as_shape().width, self.mtvec_base)
        self.mtvec_mode = CSRRegister(
            None, gen_params, width=TrapVectorMode.as_shape().width, fu_write_filtermap=filter_legal_mode
        )
        mtvec.add_field(0, self.mtvec_mode)

    def _mstatus_fields_implementation(self, gen_params: GenParams, mstatus: AliasedCSR, mstatush: AliasedCSR):
        def filter_legal_priv_mode(m: TModule, v: Value):
            legal = Signal(1)
            with m.Switch(v):
                with m.Case(PrivilegeLevel.MACHINE):
                    m.d.av_comb += legal.eq(1)
                with m.Case(PrivilegeLevel.USER):
                    m.d.av_comb += legal.eq(gen_params.user_mode)
                with m.Default():
                    m.d.av_comb += legal.eq(0)

            return (legal, v)

        # MIE bit - global interrupt enable
        self.mstatus_mie = CSRRegister(None, gen_params, width=1)
        mstatus.add_field(MstatusFieldOffsets.MIE, self.mstatus_mie)
        # MPIE bit - previous MIE
        self.mstatus_mpie = CSRRegister(None, gen_params, width=1)
        mstatus.add_field(MstatusFieldOffsets.MPIE, self.mstatus_mpie)
        # MPP field - previous priv mode
        self.mstatus_mpp = CSRRegister(
            None,
            gen_params,
            width=PrivilegeLevel.as_shape().width,
            fu_write_filtermap=filter_legal_priv_mode,
            init=PrivilegeLevel.MACHINE,
        )
        mstatus.add_field(MstatusFieldOffsets.MPP, self.mstatus_mpp)

        # Fixed MXLEN/SXLEN/UXLEN = isa.xlen
        if gen_params.isa.xlen == 64:
            # Registers only exist in RV64
            mstatus.add_read_only_field(
                MstatusFieldOffsets.UXL, XlenEncoding.as_shape().width, XlenEncoding.W64 if gen_params.user_mode else 0
            )
            mstatus.add_read_only_field(MstatusFieldOffsets.SXL, XlenEncoding.as_shape().width, 0)

        # Little-endianness
        mstatus.add_read_only_field(MstatusFieldOffsets.UBE, 1, 0)
        if gen_params.isa.xlen == 32:
            mstatush.add_read_only_field(MstatusFieldOffsets.SBE - mstatus.width, 1, 0)
            mstatush.add_read_only_field(MstatusFieldOffsets.MBE - mstatus.width, 1, 0)
        elif gen_params.isa.xlen == 64:
            mstatus.add_read_only_field(MstatusFieldOffsets.SBE, 1, 0)
            mstatus.add_read_only_field(MstatusFieldOffsets.MBE, 1, 0)

        self.mstatus_mprv = CSRRegister(None, gen_params, width=1, ro_bits=0 if gen_params.user_mode else 1)
        mstatus.add_field(MstatusFieldOffsets.MPRV, self.mstatus_mprv)

        # Supervisor mode not supported - read only 0 supervisor bits
        mstatus.add_read_only_field(MstatusFieldOffsets.SUM, 1, 0)
        mstatus.add_read_only_field(MstatusFieldOffsets.MXR, 1, 0)
        mstatus.add_read_only_field(MstatusFieldOffsets.TVM, 1, 0)
        mstatus.add_read_only_field(MstatusFieldOffsets.TSR, 1, 0)
        mstatus.add_read_only_field(MstatusFieldOffsets.SPP, 1, 0)
        mstatus.add_read_only_field(MstatusFieldOffsets.SPIE, 1, 0)
        mstatus.add_read_only_field(MstatusFieldOffsets.SIE, 1, 0)

        self.mstatus_tw = CSRRegister(None, gen_params, width=1, ro_bits=0 if gen_params.user_mode else 1)
        mstatus.add_field(MstatusFieldOffsets.TW, self.mstatus_tw)

        # Extension Context Status bits
        # future todo: implement actual state modification tracking of F and V registers and CSRs
        # State = 3 is DIRTY. Implementation is allowed to always set dirty for VS and FS, regardless of CSR updates
        mstatus.add_read_only_field(MstatusFieldOffsets.VS, 2, 3 if Extension.V in gen_params.isa.extensions else 0)
        mstatus.add_read_only_field(MstatusFieldOffsets.FS, 2, 3 if Extension.F in gen_params.isa.extensions else 0)
        mstatus.add_read_only_field(MstatusFieldOffsets.XS, 2, 0)
        # SD field - set to one when one of the states is dirty
        mstatus.add_read_only_field(
            MstatusFieldOffsets.SD % mstatus.width,  # SD is last bit of `mstatus` (depends on xlen)
            1,
            Extension.V in gen_params.isa.extensions or Extension.F in gen_params.isa.extensions,
        )

    def _misa_value(self, gen_params):
        misa_value = 0

        misa_extension_bits = {
            0: Extension.A,
            1: Extension.B,
            2: Extension.C,
            3: Extension.D,
            4: Extension.E,
            5: Extension.F,
            8: Extension.I,
            12: Extension.M,
            16: Extension.Q,
            21: Extension.V,
        }

        for bit, extension in misa_extension_bits.items():
            if extension in gen_params.isa.extensions:
                misa_value |= 1 << bit

        if gen_params.user_mode:
            misa_value |= 1 << 20
        # 7 - Hypervisor, 18 - Supervisor, 23 - Custom Extensions

        xml_field_mapping = {32: XlenEncoding.W32, 64: XlenEncoding.W64, 128: XlenEncoding.W128}
        misa_value |= xml_field_mapping[gen_params.isa.xlen] << (gen_params.isa.xlen - 2)

        return misa_value


class CSRInstances(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params

        self.m_mode = MachineModeCSRRegisters(gen_params)

        if gen_params._generate_test_hardware:
            self.csr_coreblocks_test = CSRRegister(CSRAddress.COREBLOCKS_TEST_CSR, gen_params)

        self.time = CSRRegister(CSRAddress.TIME, self.gen_params)
        self.timeh = CSRRegister(CSRAddress.TIMEH, self.gen_params)

    def elaborate(self, platform):
        m = TModule()

        m.submodules.m_mode = self.m_mode

        if self.gen_params._generate_test_hardware:
            m.submodules.csr_coreblocks_test = self.csr_coreblocks_test

        # TIME CSR is a R/O alias to Memory-Mapped `mtime` value (from clint). If `mtime` is not available,
        # then fallback to providing a cycle counter source.
        clint_mtime = DependencyContext.get().get_optional_dependency(ClintMtimeKey())
        time_counter = Signal(64)
        m.d.sync += time_counter.eq(time_counter + 1)
        time_source = time_counter if clint_mtime is None else clint_mtime

        with Transaction().body(m):
            if clint_mtime is not None:
                self.time.write(m, data=time_source[: self.time.width])
                self.timeh.write(m, data=time_source[self.time.width :])

        m.submodules.time = self.time
        m.submodules.timeh = self.timeh

        return m
