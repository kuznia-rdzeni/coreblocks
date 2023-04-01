from coreblocks.params.genparams import GenParams
from coreblocks.params.fu_params import BlockComponentParams
from coreblocks.fu.alu import ALUComponent
from coreblocks.fu.jumpbranch import JumpComponent
from coreblocks.lsu.dummyLsu import LSUBlockComponent
from coreblocks.stages.rs_func_block import RSBlockComponent

basic_configuration: list[BlockComponentParams] = [
    RSBlockComponent([ALUComponent(), JumpComponent()], rs_entries=4),
    LSUBlockComponent(),
]


class CoreConfiguration:
    isa_str: str = "rv32i"
    func_units_config: list[BlockComponentParams] = basic_configuration

    phys_reg_bits: int = 6
    rob_entries_bits: int = 7
    start_pc: int = 0


class BasicCoreConfiguration(CoreConfiguration):
    pass


class TinyCoreConfiguration(CoreConfiguration):
    func_units_config = [
        RSBlockComponent([ALUComponent(), JumpComponent()], rs_entries=2),
        LSUBlockComponent(),
    ]
    rob_entries_bits = 6


def gen_params_from_config(cfg: CoreConfiguration) -> GenParams:
    return GenParams(
        cfg.isa_str,
        cfg.func_units_config,
        phys_regs_bits=cfg.phys_reg_bits,
        rob_entries_bits=cfg.rob_entries_bits,
        start_pc=cfg.start_pc,
    )
