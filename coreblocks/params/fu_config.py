from coreblocks.fu.alu import AluFU
from coreblocks.fu.jumpbranch import JumpFU
from coreblocks.stages.rs_func_block import RSBlock

DEFAULT_FU_CONFIG = [RSBlock([AluFU(), JumpFU()], rs_entries=4)]
