from coreblocks.params.fu_params import BlockComponentParams
from coreblocks.fu.alu import ALUComponent
from coreblocks.fu.jumpbranch import JumpComponent
from coreblocks.lsu.dummyLsu import LSUBlockComponent
from coreblocks.stages.rs_func_block import RSBlockComponent

basic_configuration: list[BlockComponentParams] = [
    RSBlockComponent([ALUComponent(), JumpComponent()], rs_entries=4),
    LSUBlockComponent(),
]
