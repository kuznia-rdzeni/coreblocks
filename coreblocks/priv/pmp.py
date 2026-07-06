from amaranth import *
from amaranth.lib import data
from amaranth.lib.enum import Enum, auto, unique
from amaranth_types import HasElaborate
from transactron.core import TModule
from transactron.utils import DependencyContext, OneHotMux, assign, AssignType, make_layout

from coreblocks.arch.isa_consts import PMPAFlagEncoding, PMPCfgLayout, PrivilegeLevel
from coreblocks.interface.keys import CSRInstancesKey
from coreblocks.params import *


class PMPLayout(data.StructLayout):
    def __init__(self):
        super().__init__({"r": 1, "w": 1, "x": 1})


class PMPLayoutFull(data.StructLayout):
    def __init__(self):
        super().__init__({"r": 1, "w": 1, "x": 1, "l": 1})


@unique
class PMPOperationMode(Enum):
    LSU = auto()
    INSTRUCTION_FETCH = auto()
    MMU = auto()


class DynamicAreaPMPChecker(Elaboratable):
    """
    Implementation of physical memory protection checker that checks permissions
    of an naturally aligned power-of-two physical address range.
    """

    paddr: Value
    """
    Memory address, for which PMP checks are requested. Must be aligned to the size class.
    """

    size_class: Value
    """
    The size class for which to check uniformity and attributes. See size_classes in constructor.
    """

    uniform: Value
    """
    Is the address range fully inside a single PMP entry.
    """

    result: data.View
    """
    RWX permission bits for the given address based on current PMP configuration
    and privilege mode. Bits are set to 0 if access is denied.
    layout: PMPLayout
    """

    def __init__(self, gen_params: GenParams, *, mode: PMPOperationMode, size_classes: list[int]) -> None:
        """
        mode: PMPOperationMode
            Effective mode depends on `mode`:
            - LSU: MPRV-aware (using MPP when MPRV=1 and current mode is M)
            - INSTRUCTION_FETCH: uses only current privilege mode
            - MMU: always behaves as supervisor mode
        size_classes: list[int]
            The log2 of power-of-two for which the checker can do the operations.
            The size_class signal selects the value from these.
        """
        self.gen_params = gen_params
        self.csr = DependencyContext.get().get_dependency(CSRInstancesKey()).m_mode
        self.size_classes = size_classes
        self.mode = mode

        self.paddr = Signal(gen_params.phys_addr_bits)
        self.size_class = Signal(range(len(size_classes)))
        self.uniform = Signal()
        self.result = Signal(PMPLayout())

    def elaborate(self, platform) -> HasElaborate:
        m = TModule()

        grain = self.gen_params.pmp_grain
        n = self.gen_params.pmp_register_count

        if n == 0:
            m.d.comb += self.uniform.eq(1)
            m.d.comb += self.result.eq(PMPLayout().const({"r": 1, "w": 1, "x": 1}))
            return m

        cfgs = [data.View(PMPCfgLayout(), self.csr.pmpxcfg[i].value) for i in range(n)]
        addr_vals = [self.csr.pmpaddrx[i].value for i in range(n)]

        size_class_masks = [(1 << max(sc - 2, grain)) - 1 for sc in self.size_classes]
        size_class_mask = Array(size_class_masks)[self.size_class]

        paddr = Signal(self.gen_params.phys_addr_bits)
        m.d.comb += paddr.eq(self.paddr)
        m.d.comb += paddr[: max(grain + 2, min(self.size_classes))].eq(0)

        matches_any = Signal(n)
        matches_all = Signal(n)

        layout = make_layout(("matches_all", 1), ("entry_data", PMPLayoutFull()))
        all_data = Signal(data.ArrayLayout(layout, n))

        for i in range(n):
            is_napot = Signal()
            napot_mask = Signal(self.gen_params.phys_addr_bits - 2)
            start_bit = max(0, grain - 1)

            with m.Switch(cfgs[i].A):
                with m.Case(PMPAFlagEncoding.TOR):
                    bottom = addr_vals[i - 1][grain:] if i > 0 else 0
                    addr_hi = (self.paddr[2:] | size_class_mask) >> grain
                    m.d.comb += matches_any[i].eq((bottom <= addr_hi) & (paddr[2 + grain :] < addr_vals[i][grain:]))
                    m.d.comb += matches_all[i].eq((bottom <= paddr[2 + grain :]) & (addr_hi < addr_vals[i][grain:]))
                if grain == 0:
                    with m.Case(PMPAFlagEncoding.NA4):
                        m.d.comb += napot_mask.eq(0)
                        m.d.comb += is_napot.eq(1)
                with m.Case(PMPAFlagEncoding.NAPOT):
                    m.d.comb += napot_mask[start_bit:].eq(addr_vals[i][start_bit:] ^ (addr_vals[i][start_bit:] + 1))
                    m.d.comb += is_napot.eq(1)

            m.d.comb += napot_mask[:grain].eq(~0)

            with m.If(is_napot):
                common_mask = size_class_mask | napot_mask
                m.d.comb += matches_any[i].eq((paddr[2:] & ~common_mask) == (addr_vals[i] & ~common_mask))

                # technically should be (common_mask == napot_mask) & matches_any[i], but the implication
                # is not required for the rest of the circuit (we are only looking at first any-matching)
                m.d.comb += matches_all[i].eq(common_mask == napot_mask)  # same as napot_log2 >= size_class_log2

            m.d.comb += assign(
                all_data[i],
                {
                    "matches_all": matches_all[i],
                    "entry_data": {
                        "r": cfgs[i].R,
                        "w": cfgs[i].W,
                        "x": cfgs[i].X,
                        "l": cfgs[i].L,
                    },
                },
            )

        default_input = layout.const(
            {
                "matches_all": 1,
                "entry_data": {
                    "r": 0,
                    "w": 0,
                    "x": 0,
                    "l": 0,
                },
            }
        )

        # entry fully covers the match if all entries before the fully matching one don't match any bytes.
        # this is the same as checking the the first any-matching entry is also fully matching
        selected = OneHotMux.create(
            m, [(matches_any[i], all_data[i]) for i in range(n)], priority=True, default_input=default_input
        )

        # hardcode uniform signal if we know via grain size that it is always uniform
        # this allows the toolchain to remove half of the comparators for TOR
        if all(sc <= grain + 2 for sc in self.size_classes):
            m.d.comb += self.uniform.eq(1)
        else:
            m.d.comb += self.uniform.eq(selected.matches_all)

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

        with m.If(~self.uniform):
            m.d.comb += self.result.eq(PMPLayout().const({"r": 0, "w": 0, "x": 0}))
        if self.mode != PMPOperationMode.MMU:
            with m.Elif(~selected.entry_data.l & (effective_priv_mode == PrivilegeLevel.MACHINE)):
                m.d.comb += self.result.eq(PMPLayout().const({"r": 1, "w": 1, "x": 1}))
        with m.Else():
            m.d.comb += assign(self.result, selected.entry_data, fields=AssignType.LHS)

        return m


class PMPChecker(Elaboratable):
    """
    Like DynamicAreaPMPChecker, but with constant access size.
    """

    paddr: Value
    """
    Memory address, for which PMP checks are requested.
    """

    uniform: Value
    """
    Is the address range fully inside a single PMP entry.
    """

    result: data.View
    """
    RWX permission bits for the given address based on current PMP configuration
    and privilege mode. Bits are set to 0 if access is denied.
    layout: PMPLayout
    """

    def __init__(self, gen_params: GenParams, *, mode: PMPOperationMode, access_size_log: int = 2) -> None:
        self.paddr = Signal(gen_params.phys_addr_bits)
        self.uniform = Signal()
        self.result = Signal(PMPLayout())

        self._impl = DynamicAreaPMPChecker(gen_params, mode=mode, size_classes=[access_size_log])

    def elaborate(self, platform) -> HasElaborate:
        m = TModule()

        m.submodules.impl = self._impl

        m.d.comb += self._impl.paddr.eq(self.paddr)
        m.d.comb += self._impl.size_class.eq(0)
        m.d.comb += self.uniform.eq(self._impl.uniform)
        m.d.comb += self.result.eq(self._impl.result)

        return m
