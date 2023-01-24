from coreblocks.fu.alu import AluFU
from coreblocks.stages.rs_func_block import RSBlock

DEFAULT_FU_CONFIG = [RSBlock([AluFU()], rs_entries=4)]
