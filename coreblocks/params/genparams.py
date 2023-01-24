from typing import TypeVar, Type

from .fu_params import FuncBlockParams
from .isa import ISA

__all__ = ["GenParams"]

T = TypeVar("T")


class DependentCache:
    def __init__(self):
        self._depcache = {}

    def get(self, cls: Type[T]) -> T:
        v = self._depcache.get(cls, None)
        if v is None:
            v = self._depcache[cls] = cls(self)
        return v


class GenParams(DependentCache):
    def __init__(
        self,
        isa_str: str,
        *,
        fu_configuration: list[FuncBlockParams] | None = None,
        phys_regs_bits: int = 7,
        rob_entries_bits: int = 8,
        start_pc: int = 0,
        rs_entries: int | None = None,
        rs_block_number: int | None = None,
    ):
        super().__init__()
        self.isa = ISA(isa_str)

        if fu_configuration is None:
            from coreblocks.params.fu_config import DEFAULT_FU_CONFIG

            func_units_config = DEFAULT_FU_CONFIG
        else:
            func_units_config = fu_configuration

        required_rs_entries = 1
        for block in func_units_config:
            import coreblocks.stages.rs_func_block as rs_block

            if isinstance(block, rs_block.RSBlock):
                required_rs_entries = max(required_rs_entries, block.rs_entries)

        if rs_entries is None:
            self.rs_entries = required_rs_entries
        elif required_rs_entries <= rs_entries:
            self.rs_entries = rs_entries
        else:
            raise Exception("Not enough RS entries for this FU configuration")

        if rs_block_number is None:
            self.rs_number_bits = (len(func_units_config) - 1).bit_length()
        elif len(func_units_config) <= rs_block_number:
            self.rs_number_bits = (rs_block_number - 1).bit_length()
        else:
            raise Exception("RS block number is lower than required by FU configuration")

        self.phys_regs_bits = phys_regs_bits
        self.rob_entries_bits = rob_entries_bits
        self.rs_entries_bits = (self.rs_entries - 1).bit_length()
        self.start_pc = start_pc
