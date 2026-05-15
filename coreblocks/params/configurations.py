from coreblocks.arch.isa import Extension
from coreblocks.params.core_configuration import CoreConfiguration
from coreblocks.arch.isa_consts import SatpMode

from coreblocks.func_blocks.fu.common.rs_func_block import RSBlockComponent
from coreblocks.func_blocks.fu.common.fifo_rs import FifoRS
from coreblocks.func_blocks.fu.alu import ALUComponent
from coreblocks.func_blocks.fu.shift_unit import ShiftUnitComponent
from coreblocks.func_blocks.fu.jumpbranch import JumpComponent
from coreblocks.func_blocks.fu.mul_unit import MulComponent, MulType
from coreblocks.func_blocks.fu.div_unit import DivComponent
from coreblocks.func_blocks.fu.zbc import ZbcComponent
from coreblocks.func_blocks.fu.zbkx import ZbkxComponent
from coreblocks.func_blocks.fu.zbs import ZbsComponent
from coreblocks.func_blocks.fu.exception import ExceptionUnitComponent
from coreblocks.func_blocks.fu.priv import PrivilegedUnitComponent
from coreblocks.func_blocks.fu.lsu.dummyLsu import LSUComponent
from coreblocks.func_blocks.fu.lsu.lsu_atomic_wrapper import LSUAtomicWrapperComponent
from coreblocks.func_blocks.csr.csr_unit import CSRBlockComponent

__all__ = [
    "basic",
    "tiny",
    "small_linux",
    "full",
    "test",
]

# Default core configuration
basic = CoreConfiguration()

# Minimal core configuration
tiny = CoreConfiguration(
    embedded=True,
    func_units_config=(
        RSBlockComponent(
            [ALUComponent(), ShiftUnitComponent(), JumpComponent(), ExceptionUnitComponent()], rs_entries=2
        ),
        RSBlockComponent([LSUComponent()], rs_entries=2, rs_type=FifoRS),
    ),
    phys_regs_bits=basic.phys_regs_bits - 1,
    rob_entries_bits=basic.rob_entries_bits - 1,
    icache_enable=False,
    user_mode=False,
    supervisor_mode=False,
    supported_vm_schemes=(SatpMode.BARE,),
    pmp_grain_log=2,
)

# Basic core config with minimal additions required for Linux
small_linux = CoreConfiguration(
    func_units_config=(
        RSBlockComponent(
            [
                ALUComponent(),
                ShiftUnitComponent(),
                JumpComponent(),
                ExceptionUnitComponent(),
                PrivilegedUnitComponent(supervisor_enable=True),
            ],
            rs_entries=4,
        ),
        RSBlockComponent(
            [
                MulComponent(mul_unit_type=MulType.PIPELINED_MUL),
                DivComponent(),
            ],
            rs_entries=2,
        ),
        RSBlockComponent([LSUAtomicWrapperComponent(LSUComponent())], rs_entries=2, rs_type=FifoRS),
        CSRBlockComponent(),
    )
)

# Core configuration with all supported components
full = CoreConfiguration(
    func_units_config=(
        RSBlockComponent(
            [
                ALUComponent(zba_enable=True, zbb_enable=True, zicond_enable=True),
                ShiftUnitComponent(zbb_enable=True),
                ZbcComponent(),
                ZbkxComponent(),
                ZbsComponent(),
            ],
            rs_entries=2,  # reduced RS size to reduce impact of bad predictions
        ),
        RSBlockComponent(
            [
                ALUComponent(zba_enable=True, zbb_enable=True, zicond_enable=True),
                ShiftUnitComponent(zbb_enable=True),
                ZbcComponent(),
                ZbkxComponent(),
                ZbsComponent(),
                JumpComponent(),
                ExceptionUnitComponent(),
                PrivilegedUnitComponent(supervisor_enable=True),
            ],
            rs_entries=2,  # reduced RS size to reduce impact of bad predictions
        ),
        RSBlockComponent(
            [
                MulComponent(mul_unit_type=MulType.PIPELINED_MUL),
                DivComponent(),
            ],
            rs_entries=2,
        ),
        RSBlockComponent([LSUAtomicWrapperComponent(LSUComponent())], rs_entries=4, rs_type=FifoRS),
        CSRBlockComponent(),
    ),
    compressed=True,
    zcb=True,
    fetch_block_bytes_log=4,
    instr_buffer_size=16,
    pmp_register_count=16,
    frontend_superscalarity=2,
    announcement_superscalarity=2,
    retirement_superscalarity=2,
)

# Core configuration used in internal testbenches
test = CoreConfiguration(
    func_units_config=tuple(RSBlockComponent([], rs_entries=4) for _ in range(2)),
    rob_entries_bits=7,
    phys_regs_bits=7,
    interrupt_custom_count=2,
    interrupt_custom_edge_trig_mask=0b01,
    supported_vm_schemes=(SatpMode.BARE,),
    _implied_extensions=Extension.I,
    _generate_test_hardware=True,
)
