from dataclasses import dataclass, field
from coreblocks.params.fu_params import BlockComponentParams
from coreblocks.fu.alu import ALUComponent
from coreblocks.fu.jumpbranch import JumpComponent
from coreblocks.lsu.dummyLsu import LSUBlockComponent
from coreblocks.stages.rs_func_block import RSBlockComponent

basic_configuration: list[BlockComponentParams] = [
    RSBlockComponent([ALUComponent(), JumpComponent()], rs_entries=4),
    LSUBlockComponent(),
]


@dataclass(kw_only=True)
class CoreConfiguration:
    """
    Core configuration parameters.
    Override parameters by using keyword args in constructor or creating new subclass.

    Parameters
    ----------
    isa_str: str
        RISCV ISA string. Examples: "rv32i", "rv32izicsr". Used for instruction decoding.
    func_units_config: list[BlockComponentParams]
        Configuration of Functional Units and Reservation Stations.
        Example: [ RSBlockComponent([ALUComponent()], rs_entries=4), LSUBlockComponent()]
    phys_regs_bits: int
        Size of the Physical Register File is 2**phys_regs_bits.
    rob_entries_bits: int
        Size of the Reorder Buffer is 2**rob_entries_bits.
    start_pc: int
        Initial Program Counter value.
    """

    isa_str: str = "rv32i"
    func_units_config: list[BlockComponentParams] = field(default_factory=lambda: basic_configuration)

    phys_regs_bits: int = 6
    rob_entries_bits: int = 7
    start_pc: int = 0


class BasicCoreConfig(CoreConfiguration):
    """Default core configuration."""

    pass


class TinyCoreConfig(CoreConfiguration):
    """Minmal core configuration."""

    func_units_config = [
        RSBlockComponent([ALUComponent(), JumpComponent()], rs_entries=2),
        LSUBlockComponent(),
    ]
    rob_entries_bits = 6


class TestCoreConfig(CoreConfiguration):
    """Core configuration used in internal testbenches"""

    phys_regs_bits = 7
    rob_entries_bits = 7
    func_units_config = [RSBlockComponent([], rs_entries=4) for _ in range(2)]
