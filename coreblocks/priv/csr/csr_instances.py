from amaranth import *
from amaranth_types import ValueLike
from typing import Optional

from transactron.core import TModule, Transaction
from transactron.utils import DependencyContext

from coreblocks.arch import CSRAddress
from coreblocks.arch.csr_address import (
    CounterEnableFieldOffsets,
    MenvcfgFieldOffsets,
    MstatusFieldOffsets,
    sstatus_field_subset,
    PMPXCFG_WIDTH,
)
from coreblocks.arch.isa import Extension
from coreblocks.arch.isa_consts import (
    PrivilegeLevel,
    SatpMode,
    TrapVectorMode,
    XlenEncoding,
)
from coreblocks.params.genparams import GenParams
from coreblocks.priv.csr.aliased import AliasedCSR
from coreblocks.priv.csr.csr_register import CSRRegister, CSRRegisterBase
from coreblocks.priv.csr.double_counter import DoubleCounterCSR
from coreblocks.priv.csr.shadow import ShadowCSR
from coreblocks.socks.clint import ClintMtimeKey
from coreblocks.interface.keys import CSRInstancesKey


def counteren_writable_mask(hpm_counters_count: int) -> int:
    counter_list = [
        CounterEnableFieldOffsets.CY,
        CounterEnableFieldOffsets.TM,
        CounterEnableFieldOffsets.IR,
    ] + list(range(CounterEnableFieldOffsets.HPM3, CounterEnableFieldOffsets.HPM3 + hpm_counters_count))

    mask = 0
    for counter in counter_list:
        mask |= 1 << counter
    return mask


def counteren_access_filter(gen_params: GenParams, counteren_bit: int):
    def _filter(m: TModule, priv_mode: Value) -> ValueLike:
        csr_instances = DependencyContext.get().get_dependency(CSRInstancesKey())

        mcounteren = csr_instances.m_mode.mcounteren.read(m).data
        machine_disallowed = (priv_mode < PrivilegeLevel.MACHINE) & ~mcounteren[counteren_bit]

        supervisor_disallowed = 0
        if gen_params.supervisor_mode:
            scounteren = csr_instances.s_mode.scounteren.read(m).data
            supervisor_disallowed = (priv_mode < PrivilegeLevel.SUPERVISOR) & ~scounteren[counteren_bit]

        return ~(machine_disallowed | supervisor_disallowed)

    return _filter


class MachineModeCSRRegisters(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.mvendorid = CSRRegister(CSRAddress.MVENDORID, gen_params, init=0)
        self.marchid = CSRRegister(CSRAddress.MARCHID, gen_params, init=gen_params.marchid)
        self.mimpid = CSRRegister(CSRAddress.MIMPID, gen_params, init=gen_params.mimpid)
        self.mhartid = CSRRegister(CSRAddress.MHARTID, gen_params, init=0)
        self.mscratch = CSRRegister(CSRAddress.MSCRATCH, gen_params)
        self.mconfigptr = CSRRegister(CSRAddress.MCONFIGPTR, gen_params, init=0)

        self.mstatus = AliasedCSR(CSRAddress.MSTATUS, gen_params)
        self.mstatush = None
        if gen_params.isa.xlen == 32:
            self.mstatush = AliasedCSR(CSRAddress.MSTATUSH, gen_params)

        self.menvcfg = self.menvcfgh = None
        if gen_params.user_mode:
            self.menvcfg = AliasedCSR(CSRAddress.MENVCFG, gen_params)
            if gen_params.isa.xlen == 32:
                self.menvcfgh = AliasedCSR(CSRAddress.MENVCFGH, gen_params)

        self.mcause = CSRRegister(CSRAddress.MCAUSE, gen_params)
        # CY/TM/IR bits are writable, unsupported HPM bits are read-only zero.
        counteren_writeable = counteren_writable_mask(gen_params.hpm_counters_count)
        self.mcounteren = CSRRegister(
            CSRAddress.MCOUNTEREN,
            gen_params,
            ro_bits=~counteren_writeable,
        )

        self.mtvec = AliasedCSR(CSRAddress.MTVEC, gen_params)

        mepc_ro_bits = 0b1 if Extension.ZCA in gen_params.isa.extensions else 0b11  # pc alignment (SPEC)
        self.mepc = CSRRegister(CSRAddress.MEPC, gen_params, ro_bits=mepc_ro_bits)

        self.mtval = CSRRegister(CSRAddress.MTVAL, gen_params)

        self.misa = CSRRegister(
            CSRAddress.MISA,
            gen_params,
            init=self._misa_value(gen_params),
            ro_bits=(1 << gen_params.isa.xlen) - 1,
        )

        self.mcycle = DoubleCounterCSR(
            gen_params,
            CSRAddress.MCYCLE,
            CSRAddress.MCYCLEH if gen_params.isa.xlen == 32 else None,
            CSRAddress.CYCLE,
            CSRAddress.CYCLEH if gen_params.isa.xlen == 32 else None,
            shadow_access_filter=counteren_access_filter(gen_params, CounterEnableFieldOffsets.CY),
        )

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
        pmpaddrx_ro_mask = (1 << gen_params.pmp_grain) - 1
        for i in range(gen_params.pmp_register_count):
            reg = CSRRegister(getattr(CSRAddress, f"PMPADDR{i}"), gen_params, ro_bits=pmpaddrx_ro_mask)
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
        self._menvcfg_fields_implementation(gen_params, self.menvcfg, self.menvcfgh)
        self._mtvec_fields_implementation(gen_params, self.mtvec)

        # future todo: add mhpm{counter,event} CSRs

    def elaborate(self, platform):
        m = TModule()

        for name, value in vars(self).items():
            if isinstance(value, (CSRRegisterBase, DoubleCounterCSR)):
                m.submodules[name] = value

        with Transaction().body(m):
            self.mcycle.increment(m)

        return m

    def _menvcfg_fields_implementation(
        self, gen_params: GenParams, menvcfg: Optional[AliasedCSR], menvcfgh: Optional[AliasedCSR]
    ):
        self.menvcfg_fiom = None
        if menvcfg is None:
            return

        fiom_ro = gen_params.vmem_params.supported_schemes == {SatpMode.BARE}
        self.menvcfg_fiom = CSRRegister(None, gen_params, width=1, ro_bits=1 if fiom_ro else 0)
        menvcfg.add_field(MenvcfgFieldOffsets.FIOM, self.menvcfg_fiom)

    def _mtvec_fields_implementation(self, gen_params: GenParams, mtvec: AliasedCSR):
        def filter_legal_mode(m: TModule, v: Value):
            legal = Signal(1)
            m.d.av_comb += legal.eq((v == TrapVectorMode.DIRECT) | (v == TrapVectorMode.VECTORED))
            return (legal, v)

        self.mtvec_base = CSRRegister(None, gen_params, width=gen_params.isa.xlen - 2)
        mtvec.add_field(TrapVectorMode.as_shape().width, self.mtvec_base)
        self.mtvec_mode = CSRRegister(
            None,
            gen_params,
            width=TrapVectorMode.as_shape().width,
            fu_write_filtermap=filter_legal_mode,
        )
        mtvec.add_field(0, self.mtvec_mode)

    def _mstatus_fields_implementation(
        self,
        gen_params: GenParams,
        mstatus: AliasedCSR,
        mstatush: Optional[AliasedCSR],
    ):
        def filter_legal_priv_mode(m: TModule, v: Value):
            legal = Signal(1)
            with m.Switch(v):
                with m.Case(PrivilegeLevel.MACHINE):
                    m.d.av_comb += legal.eq(1)
                with m.Case(PrivilegeLevel.SUPERVISOR):
                    m.d.av_comb += legal.eq(gen_params.supervisor_mode)
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
                MstatusFieldOffsets.UXL,
                XlenEncoding.as_shape().width,
                XlenEncoding.W64 if gen_params.user_mode else 0,
            )
            mstatus.add_read_only_field(
                MstatusFieldOffsets.SXL,
                XlenEncoding.as_shape().width,
                XlenEncoding.W64 if gen_params.supervisor_mode else 0,
            )

        # Little-endianness
        mstatus.add_read_only_field(MstatusFieldOffsets.UBE, 1, 0)
        if gen_params.isa.xlen == 32:
            assert mstatush
            mstatush.add_read_only_field(MstatusFieldOffsets.SBE - mstatus.width, 1, 0)
            mstatush.add_read_only_field(MstatusFieldOffsets.MBE - mstatus.width, 1, 0)
        elif gen_params.isa.xlen == 64:
            mstatus.add_read_only_field(MstatusFieldOffsets.SBE, 1, 0)
            mstatus.add_read_only_field(MstatusFieldOffsets.MBE, 1, 0)

        self.mstatus_mprv = CSRRegister(None, gen_params, width=1, ro_bits=0 if gen_params.user_mode else 1)
        mstatus.add_field(MstatusFieldOffsets.MPRV, self.mstatus_mprv)

        # Shared mstatus/sstatus fields
        sum_ro = gen_params.vmem_params.supported_schemes == {SatpMode.BARE}
        self.mstatus_sum = CSRRegister(None, gen_params, width=1, ro_bits=1 if sum_ro else 0)
        mstatus.add_field(MstatusFieldOffsets.SUM, self.mstatus_sum)
        self.mstatus_mxr = CSRRegister(None, gen_params, width=1, ro_bits=0 if gen_params.supervisor_mode else 1)
        mstatus.add_field(MstatusFieldOffsets.MXR, self.mstatus_mxr)
        self.mstatus_tvm = CSRRegister(None, gen_params, width=1, ro_bits=0 if gen_params.supervisor_mode else 1)
        mstatus.add_field(MstatusFieldOffsets.TVM, self.mstatus_tvm)
        self.mstatus_tsr = CSRRegister(None, gen_params, width=1, ro_bits=0 if gen_params.supervisor_mode else 1)
        mstatus.add_field(MstatusFieldOffsets.TSR, self.mstatus_tsr)

        self.mstatus_spp = CSRRegister(None, gen_params, width=1, ro_bits=0 if gen_params.supervisor_mode else 1)
        mstatus.add_field(MstatusFieldOffsets.SPP, self.mstatus_spp)

        self.mstatus_spie = CSRRegister(None, gen_params, width=1, ro_bits=0 if gen_params.supervisor_mode else 1)
        mstatus.add_field(MstatusFieldOffsets.SPIE, self.mstatus_spie)

        self.mstatus_sie = CSRRegister(None, gen_params, width=1, ro_bits=0 if gen_params.supervisor_mode else 1)
        mstatus.add_field(MstatusFieldOffsets.SIE, self.mstatus_sie)

        self.mstatus_tw = CSRRegister(None, gen_params, width=1, ro_bits=0 if gen_params.user_mode else 1)
        mstatus.add_field(MstatusFieldOffsets.TW, self.mstatus_tw)

        # Extension Context Status bits
        # TODO: implement actual state modification tracking of F and V registers and CSRs
        # State = 3 is DIRTY. Implementation is allowed to always set dirty for VS and FS, regardless of CSR updates
        mstatus.add_read_only_field(
            MstatusFieldOffsets.VS,
            2,
            3 if Extension.V in gen_params.isa.extensions else 0,
        )
        mstatus.add_read_only_field(
            MstatusFieldOffsets.FS,
            2,
            3 if Extension.F in gen_params.isa.extensions else 0,
        )
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

        if gen_params.supervisor_mode:
            misa_value |= 1 << 18

        if gen_params.user_mode:
            misa_value |= 1 << 20
        # 7 - Hypervisor, 23 - Custom Extensions

        xml_field_mapping = {32: XlenEncoding.W32, 64: XlenEncoding.W64, 128: XlenEncoding.W128}
        misa_value |= xml_field_mapping[gen_params.isa.xlen] << (gen_params.isa.xlen - 2)

        return misa_value


class SupervisorModeCSRRegisters(Elaboratable):
    """Supervisor-mode CSR block with status, envcfg, trap, and SATP support."""

    def __init__(self, gen_params: GenParams, m_mode: MachineModeCSRRegisters):
        self.sscratch = CSRRegister(CSRAddress.SSCRATCH, gen_params)
        self.sstatus = ShadowCSR(
            CSRAddress.SSTATUS,
            gen_params,
            m_mode.mstatus,
            mask=self._sstatus_mask(gen_params),
        )
        self.senvcfg = AliasedCSR(CSRAddress.SENVCFG, gen_params)
        self.scause = CSRRegister(CSRAddress.SCAUSE, gen_params)
        self.stvec = AliasedCSR(CSRAddress.STVEC, gen_params)

        sepc_ro_bits = 0b1 if Extension.C in gen_params.isa.extensions else 0b11
        self.sepc = CSRRegister(CSRAddress.SEPC, gen_params, ro_bits=sepc_ro_bits)
        self.stval = CSRRegister(CSRAddress.STVAL, gen_params)

        satp_layout = gen_params.vmem_params.satp_layout

        def satp_access_valid(m, priv_mode):
            valid = Signal()
            with m.Switch(priv_mode):
                with m.Case(PrivilegeLevel.MACHINE):
                    m.d.av_comb += valid.eq(1)
                with m.Case(PrivilegeLevel.SUPERVISOR):
                    tvm = m_mode.mstatus_tvm.read(m).data
                    m.d.av_comb += valid.eq(~tvm)
                with m.Default():
                    m.d.av_comb += valid.eq(0)
            return valid

        def satp_write_filter(m: TModule, v: Value):
            satp_v = satp_layout(v)

            legal = Signal()
            with m.Switch(satp_v.mode):
                for mode in gen_params.vmem_params.supported_schemes:
                    with m.Case(mode):
                        m.d.av_comb += legal.eq(1)
                with m.Default():
                    m.d.av_comb += legal.eq(0)

            return (legal, v)

        if gen_params.vmem_params.supported_schemes == {SatpMode.BARE}:
            satp_ro = ~0
        else:
            # only allow writing to ASID bits that are implemented
            satp_ro = satp_layout.const(
                {
                    "mode": 0,
                    "asid": -(1 << gen_params.vmem_params.asidlen),
                    "ppn": 0,
                }
            ).as_bits()

        self.satp = CSRRegister(
            CSRAddress.SATP,
            gen_params,
            fu_write_filtermap=satp_write_filter,
            ro_bits=satp_ro,
            fu_access_filter=satp_access_valid,
        )
        satp_v = gen_params.vmem_params.satp_layout(self.satp.value)
        self.satp_mode = satp_v.mode
        self.satp_asid = satp_v.asid
        self.satp_ppn = satp_v.ppn

        # CY/TM/IR bits are writable, unsupported HPM bits are read-only zero.
        counteren_writeable = counteren_writable_mask(gen_params.hpm_counters_count)
        self.scounteren = CSRRegister(
            CSRAddress.SCOUNTEREN,
            gen_params,
            ro_bits=~counteren_writeable,
        )

        self._senvcfg_fields_implementation(gen_params, self.senvcfg)
        self._stvec_fields_implementation(gen_params, self.stvec)

    def _senvcfg_fields_implementation(self, gen_params: GenParams, senvcfg: AliasedCSR):
        fiom_ro = gen_params.vmem_params.supported_schemes == {SatpMode.BARE}
        self.senvcfg_fiom = CSRRegister(None, gen_params, width=1, ro_bits=1 if fiom_ro else 0)
        senvcfg.add_field(MenvcfgFieldOffsets.FIOM, self.senvcfg_fiom)

    def _stvec_fields_implementation(self, gen_params: GenParams, stvec: AliasedCSR):
        def filter_legal_mode(m: TModule, v: Value):
            legal = Signal(1)
            m.d.av_comb += legal.eq((v == TrapVectorMode.DIRECT) | (v == TrapVectorMode.VECTORED))
            return (legal, v)

        self.stvec_base = CSRRegister(None, gen_params, width=gen_params.isa.xlen - 2)
        stvec.add_field(TrapVectorMode.as_shape().width, self.stvec_base)
        self.stvec_mode = CSRRegister(
            None,
            gen_params,
            width=TrapVectorMode.as_shape().width,
            fu_write_filtermap=filter_legal_mode,
        )
        stvec.add_field(0, self.stvec_mode)

    def _sstatus_mask(self, gen_params):
        mask = 0
        for field in sstatus_field_subset:
            if gen_params.isa.xlen == 32 and field == MstatusFieldOffsets.UXL:
                continue  # UXL field does not exist in RV32

            field_offset = field.value % gen_params.isa.xlen
            mask |= ((1 << field.field_length()) - 1) << field_offset
        return mask

    def elaborate(self, platform):
        m = TModule()

        for name, value in vars(self).items():
            if isinstance(value, (CSRRegisterBase, DoubleCounterCSR)):
                m.submodules[name] = value

        return m


class CSRInstances(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params

        self.m_mode = MachineModeCSRRegisters(gen_params)
        if gen_params.supervisor_mode:
            self.s_mode = SupervisorModeCSRRegisters(gen_params, self.m_mode)

        if gen_params._generate_test_hardware:
            self.csr_coreblocks_test = CSRRegister(CSRAddress.COREBLOCKS_TEST_CSR, gen_params)

        self.time = CSRRegister(
            CSRAddress.TIME,
            self.gen_params,
            fu_access_filter=counteren_access_filter(self.gen_params, CounterEnableFieldOffsets.TM),
        )
        if gen_params.isa.xlen == 32:
            self.timeh = CSRRegister(
                CSRAddress.TIMEH,
                self.gen_params,
                fu_access_filter=counteren_access_filter(self.gen_params, CounterEnableFieldOffsets.TM),
            )

    def elaborate(self, platform):
        m = TModule()

        m.submodules.m_mode = self.m_mode
        if self.gen_params.supervisor_mode:
            m.submodules.s_mode = self.s_mode

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
                if self.gen_params.isa.xlen == 32:
                    self.timeh.write(m, data=time_source[self.time.width :])

        m.submodules.time = self.time
        if self.gen_params.isa.xlen == 32:
            m.submodules.timeh = self.timeh

        return m
