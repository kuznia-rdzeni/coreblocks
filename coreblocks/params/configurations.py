from collections.abc import Collection
import dataclasses
from dataclasses import dataclass, field
from typing import Self
from transactron.utils._typing import type_self_kwargs_as

from coreblocks.arch.isa import Extension
from coreblocks.params.fu_params import BlockComponentParams

from coreblocks.func_blocks.fu.common.rs_func_block import RSBlockComponent
from coreblocks.func_blocks.fu.common.fifo_rs import FifoRS
from coreblocks.func_blocks.fu.alu import ALUComponent
from coreblocks.func_blocks.fu.shift_unit import ShiftUnitComponent
from coreblocks.func_blocks.fu.jumpbranch import JumpComponent
from coreblocks.func_blocks.fu.mul_unit import MulComponent, MulType
from coreblocks.func_blocks.fu.div_unit import DivComponent
from coreblocks.func_blocks.fu.zbc import ZbcComponent
from coreblocks.func_blocks.fu.zbs import ZbsComponent
from coreblocks.func_blocks.fu.exception import ExceptionUnitComponent
from coreblocks.func_blocks.fu.priv import PrivilegedUnitComponent
from coreblocks.func_blocks.fu.lsu.dummyLsu import LSUComponent
from coreblocks.func_blocks.fu.lsu.pma import PMARegion
from coreblocks.func_blocks.csr.csr import CSRBlockComponent


__all__ = ["CoreConfiguration", "basic_core_config", "tiny_core_config", "full_core_config", "test_core_config"]

basic_configuration: tuple[BlockComponentParams, ...] = (
    RSBlockComponent(
        [ALUComponent(), ShiftUnitComponent(), JumpComponent(), ExceptionUnitComponent(), PrivilegedUnitComponent()],
        rs_entries=4,
    ),
    RSBlockComponent([LSUComponent()], rs_entries=2, rs_type=FifoRS),
    CSRBlockComponent(),
)


@dataclass(kw_only=True)
class _CoreConfigurationDataClass:
    """
    Core configuration parameters.

    Parameters
    ----------
    xlen: int
        Bit width of Core.
    func_units_config: Collection[BlockComponentParams]
        Configuration of Functional Units and Reservation Stations.
        Example: [RSBlockComponent([ALUComponent()], rs_entries=4), LSUBlockComponent()]
    compressed: bool
        Enables 16-bit Compressed Instructions extension.
    embedded: bool
        Enables Reduced Integer (E) extension.
    marchid: int
        The value of the MARCHID CSR.
    mimpid: int
        The value of the MIMPID CSR.
    debug_signals: bool
        Enable debug signals (for example hardware metrics etc). If disabled, none of them will be synthesized.
    phys_regs_bits: int
        Size of the Physical Register File is 2**phys_regs_bits.
    rob_entries_bits: int
        Size of the Reorder Buffer is 2**rob_entries_bits.
    start_pc: int
        Initial Program Counter value.
    icache_enable: bool
        Enable instruction cache. If disabled, requestes are bypassed directly to the bus.
    icache_ways: int
        Associativity of the instruction cache.
    icache_sets_bits: int
        Log of the number of sets of the instruction cache.
    icache_line_bytes_log: int
        Log of the cache line size (in bytes).
    fetch_block_bytes_log: int
        Log of the size of the fetch block (in bytes).
    instr_buffer_size: int
        Size of the instruction buffer.
    interrupt_custom_count: int
        Number of custom/local async interrupts to support. First interrupt will be registered at id 16.
    interrupt_custom_edge_trig_mask: int
        Bit mask specifing if interrupt should be edge or level triggered. If nth bit is set to 1, interrupt
        with id 16+n will be considered as edge triggered and clearable via `mip`. In other case bit `mip` is
        read-only and directly connected to input signal (implementation must provide clearing method)
    allow_partial_extensions: bool
        Allow partial support of extensions.
    extra_verification: bool
        Enables generation of additional hardware checks (asserts via logging system). Defaults to True.
    _implied_extensions: Extenstion
        Bit flag specifing enabled extenstions that are not specified by func_units_config. Used in internal tests.
    _generate_test_hardware: bool
        Enables generation of additional hardware used for use in internal unit tests.
    pma : list[PMARegion]
        Definitions of PMAs per contiguous segments of memory.
    """

    def __post_init__(self):
        self.func_units_config = [
            dataclasses.replace(conf, rs_number=k) if hasattr(conf, "rs_number") else conf
            for k, conf in enumerate(self.func_units_config)
        ]

    xlen: int = 32
    func_units_config: Collection[BlockComponentParams] = basic_configuration

    compressed: bool = False
    embedded: bool = False

    marchid: int = 44
    mimpid: int = 0

    debug_signals: bool = True

    phys_regs_bits: int = 6
    rob_entries_bits: int = 7
    start_pc: int = 0

    icache_enable: bool = True
    icache_ways: int = 2
    icache_sets_bits: int = 7
    icache_line_bytes_log: int = 5

    fetch_block_bytes_log: int = 2

    instr_buffer_size: int = 4
    ftq_size_log: int = 4
    bpu_global_history_len: int = 16

    interrupt_custom_count: int = 0
    interrupt_custom_edge_trig_mask: int = 0

    allow_partial_extensions: bool = False

    extra_verification: bool = True

    _implied_extensions: Extension = Extension(0)
    _generate_test_hardware: bool = False

    pma: list[PMARegion] = field(default_factory=list)


class CoreConfiguration(_CoreConfigurationDataClass):
    @type_self_kwargs_as(_CoreConfigurationDataClass.__init__)
    def replace(self, **kwargs) -> Self:
        return dataclasses.replace(self, **kwargs)


# Default core configuration
basic_core_config = CoreConfiguration()

# Minimal core configuration
tiny_core_config = CoreConfiguration(
    embedded=True,
    func_units_config=(
        RSBlockComponent([ALUComponent(), ShiftUnitComponent(), JumpComponent()], rs_entries=2),
        RSBlockComponent([LSUComponent()], rs_entries=2, rs_type=FifoRS),
    ),
    phys_regs_bits=basic_core_config.phys_regs_bits - 1,
    rob_entries_bits=basic_core_config.rob_entries_bits - 1,
    allow_partial_extensions=True,  # No exception unit
)

# Core configuration with all supported components
full_core_config = CoreConfiguration(
    func_units_config=(
        RSBlockComponent(
            [
                ALUComponent(zba_enable=True, zbb_enable=True),
                ShiftUnitComponent(zbb_enable=True),
                ZbcComponent(),
                ZbsComponent(),
                JumpComponent(),
                ExceptionUnitComponent(),
                PrivilegedUnitComponent(),
            ],
            rs_entries=4,
        ),
        RSBlockComponent(
            [
                MulComponent(mul_unit_type=MulType.SEQUENCE_MUL),
                DivComponent(),
            ],
            rs_entries=2,
        ),
        RSBlockComponent([LSUComponent()], rs_entries=4, rs_type=FifoRS),
        CSRBlockComponent(),
    ),
    compressed=True,
    fetch_block_bytes_log=4,
    instr_buffer_size=16,
    bpu_global_history_len=64,
)

# Core configuration used in internal testbenches
test_core_config = CoreConfiguration(
    func_units_config=tuple(RSBlockComponent([], rs_entries=4) for _ in range(2)),
    rob_entries_bits=7,
    phys_regs_bits=7,
    interrupt_custom_count=2,
    interrupt_custom_edge_trig_mask=0b01,
    _implied_extensions=Extension.I,
    _generate_test_hardware=True,
)
