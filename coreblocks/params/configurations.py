from coreblocks.params.fu_params import BlockComponentParams
from coreblocks.stages.rs_func_block import RSBlockComponent
from coreblocks.fu.alu import ALUComponent
from coreblocks.fu.jumpbranch import JumpComponent
from coreblocks.fu.mul_unit import MulComponent, MulType
from coreblocks.lsu.dummyLsu import LSUBlockComponent
from coreblocks.structs_common.csr import CSRBlockComponent

basic_configuration: list[BlockComponentParams] = [
    RSBlockComponent([ALUComponent(), JumpComponent()], rs_entries=4),
    LSUBlockComponent(),
]

# Example configuration with all supported components
extended_configuration: list[BlockComponentParams] = [
    RSBlockComponent([ALUComponent(), JumpComponent(), MulComponent(mul_unit_type=MulType.SHIFT_MUL)], rs_entries=4),
    LSUBlockComponent(),
    CSRBlockComponent(),
]
