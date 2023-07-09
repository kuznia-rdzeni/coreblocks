from amaranth.utils import *
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from coreblocks.params.configurations import VectorUnitConfiguration

__all__ = ["VectorParameters"]


class VectorParameters:
    def __init__(self, cfg: "VectorUnitConfiguration"):
        self.elen = cfg.elen
        self.vlen = cfg.vlen
        self.vrp_count = cfg.vrp_count
        self.vrp_count_bits = log2_int(self.vrp_count, False)
        self.register_bank_count = cfg.register_bank_count
        self.vxrs_entries = cfg.vxrs_entries
        self.vvrs_entries = cfg.vvrs_entries

        self.bytes_in_vlen = self.vlen // 8
        self.bytes_in_elen = self.elen // 8

        accepted_elens = {8, 16, 32, 64}
        if self.elen not in accepted_elens:
            raise ValueError(f"Wrong ELEN value. Got: {self.elen}, expected one of: {accepted_elens}")

        if self.vlen % self.elen != 0:
            raise ValueError("Wrong vectors parameters. VLEN should be divisable by ELEN")

        self.elems_in_vlen = self.vlen // self.elen

        if self.elems_in_vlen % self.register_bank_count != 0:
            raise ValueError("Number of elements in vector register not divisable by number of banks.")

        self.elems_in_bank = self.elems_in_vlen // self.register_bank_count
        self.elems_in_bank_bits = log2_int(self.elems_in_bank, False)
        # vstart have to have enough bits to hold all indicies for minimum SEW and maximum LMUL
        # minimum SEW is 1 byte and maximum LMUL is 8
        self.vstart_bits = log2_int(self.bytes_in_vlen * 8, False)
        self.vvrs_entries_bits = log2_int(self.vvrs_entries, False)

        self.max_lmul = 8
