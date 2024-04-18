from collections.abc import Collection

import dataclasses
from dataclasses import dataclass, field

from typing import Self
from transactron.utils._typing import type_self_kwargs_as

from coreblocks.params.isa_params import Extension
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
    allow_partial_extensions: bool
        Allow partial support of extensions.
    _implied_extensions: Extenstion
        Bit flag specifing enabled extenstions that are not specified by func_units_config. Used in internal tests.
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

    debug_signals: bool = True

    phys_regs_bits: int = 6
    rob_entries_bits: int = 7
    start_pc: int = 0

    icache_enable: bool = True
    icache_ways: int = 2
    icache_sets_bits: int = 7
    icache_line_bytes_log: int = 5

    fetch_block_bytes_log: int = 2

    allow_partial_extensions: bool = False

    _implied_extensions: Extension = Extension(0)

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
    fetch_block_bytes_log=2,
)

# Core configuration used in internal testbenches
test_core_config = CoreConfiguration(
    func_units_config=tuple(RSBlockComponent([], rs_entries=4) for _ in range(2)),
    rob_entries_bits=7,
    phys_regs_bits=7,
    _implied_extensions=Extension.I,
)
