from amaranth import *

from transactron.utils import ValueLike

from coreblocks.params import GenParams

__all__ = ["FrontendParams"]


class FrontendParams:
    def __init__(self, gen_params: GenParams):
        self.gp = gen_params

    def fb_addr(self, pc: ValueLike) -> Value:
        """Returns the fetch block address of a given PC."""
        return Value.cast(pc)[self.gp.fetch_block_bytes_log :]

    def fb_instr_idx(self, pc: ValueLike) -> Value:
        """Returns the index of an instruction in a fetch block for a given instruction PC."""
        return Value.cast(pc)[self.gp.min_instr_width_bytes_log : self.gp.fetch_block_bytes_log]

    def pc_from_fb(self, fb_addr: ValueLike, fb_instr_idx: int | Value) -> Value:
        """For a given fetch block address and an instruction index, returns the instruction's PC."""
        if isinstance(fb_instr_idx, int):
            fb_instr_idx = C(fb_instr_idx, self.gp.fetch_width_log)
        assert len(fb_instr_idx) == self.gp.fetch_width_log
        return Cat(C(0, self.gp.min_instr_width_bytes_log), fb_instr_idx, fb_addr)
