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
        func_units_config: list[FuncBlockParams] | None = None,
        phys_regs_bits: int = 7,
        rob_entries_bits: int = 8,
        start_pc: int = 0,
    ):
        super().__init__()
        self.isa = ISA(isa_str)

        if func_units_config is None:
            from coreblocks.params.fu_config import DEFAULT_FU_CONFIG

            self.func_units_config = DEFAULT_FU_CONFIG
        else:
            self.func_units_config = func_units_config

        self.rs_entries = 1
        for block in self.func_units_config:
            import coreblocks.stages.rs_func_block as rs_block

            if isinstance(block, rs_block.RSBlock):
                self.rs_entries = max(self.rs_entries, block.rs_entries)

        self.rs_number_bits = (len(self.func_units_config) - 1).bit_length()

        self.phys_regs_bits = phys_regs_bits
        self.rob_entries_bits = rob_entries_bits
        self.rs_entries_bits = (self.rs_entries - 1).bit_length()
        self.start_pc = start_pc
