from collections.abc import Collection
import dataclasses
from dataclasses import dataclass

from coreblocks.params.isa import Extension
from coreblocks.params.fu_params import BlockComponentParams
from coreblocks.stages.rs_func_block import RSBlockComponent

from coreblocks.fu.alu import ALUComponent
from coreblocks.fu.shift_unit import ShiftUnitComponent
from coreblocks.fu.jumpbranch import JumpComponent
from coreblocks.fu.mul_unit import MulComponent, MulType
from coreblocks.lsu.dummyLsu import LSUBlockComponent
from coreblocks.structs_common.csr import CSRBlockComponent

__all__ = ["CoreConfiguration", "basic_core_config", "tiny_core_config", "full_core_config", "test_core_config"]

basic_configuration: tuple[BlockComponentParams, ...] = (
    RSBlockComponent([ALUComponent(), ShiftUnitComponent(), JumpComponent()], rs_entries=4),
    LSUBlockComponent(),
)


@dataclass(kw_only=True)
class CoreConfiguration:
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
    icache_block_size_bits: int
        Log of the cache line size (in bytes).
    allow_partial_extensions: bool
        Allow partial support of extensions.
    _implied_extensions: Extenstion
        Bit flag specifing enabled extenstions that are not specified by func_units_config. Used in internal tests.
    """

    xlen: int = 32
    func_units_config: Collection[BlockComponentParams] = basic_configuration

    compressed: bool = False
    embedded: bool = False

    phys_regs_bits: int = 6
    rob_entries_bits: int = 7
    start_pc: int = 0

    icache_enable: bool = True
    icache_ways: int = 2
    icache_sets_bits: int = 7
    icache_block_size_bits: int = 5

    allow_partial_extensions: bool = True  # TODO: Change to False when I extension will be fully supported

    _implied_extensions: Extension = Extension(0)

    def replace(self, **kwargs):
        return dataclasses.replace(self, **kwargs)


# Default core configuration
basic_core_config = CoreConfiguration()

# Minimal core configuration
tiny_core_config = CoreConfiguration(
    func_units_config=(
        RSBlockComponent([ALUComponent(), ShiftUnitComponent(), JumpComponent()], rs_entries=2),
        LSUBlockComponent(),
    ),
    rob_entries_bits=6,
)

# Core configuration with all supported components
full_core_config = CoreConfiguration(
    func_units_config=(
        RSBlockComponent([ALUComponent(zba_enable=True), ShiftUnitComponent(), JumpComponent()], rs_entries=4),
        RSBlockComponent([MulComponent(mul_unit_type=MulType.SEQUENCE_MUL)], rs_entries=4),
        LSUBlockComponent(),
        CSRBlockComponent(),
    ),
)

# Core configuration used in internal testbenches
test_core_config = CoreConfiguration(
    func_units_config=tuple(RSBlockComponent([], rs_entries=4) for _ in range(2)),
    rob_entries_bits=7,
    phys_regs_bits=7,
    _implied_extensions=Extension.I,
)
