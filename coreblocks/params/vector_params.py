from amaranth.utils import *
from typing import TYPE_CHECKING
from coreblocks.params.isa import EEW, eew_to_bits

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
        self.vxrs_entries = 8 # placeholder to be updated by VectorBlockComponent
        self.vvrs_entries = cfg.vvrs_entries

        self.bytes_in_vlen = self.vlen // 8
        self.bytes_in_elen = self.elen // 8

        accepted_elens = {8, 16, 32, 64}
        if self.elen not in accepted_elens:
            raise ValueError(f"Wrong ELEN value. Got: {self.elen}, expected one of: {accepted_elens}")

        if self.vlen % self.elen != 0:
            raise ValueError("Wrong vectors parameters. VLEN should be divisable by ELEN")

        self.elens_in_vlen = self.vlen // self.elen

        if self.elens_in_vlen % self.register_bank_count != 0:
            raise ValueError("Number of elements in vector register not divisable by number of banks.")

        self.elens_in_bank = self.elens_in_vlen // self.register_bank_count
        self.elens_in_bank_bits = bits_for(self.elens_in_bank, False)

        self.eew_to_elems_in_bank = {eew: self.vlen // eew_to_bits(eew) // self.register_bank_count for eew in EEW}
        self.eew_to_elems_in_bank_bits = {eew: bits_for(self.eew_to_elems_in_bank[eew]) for eew in EEW}
        # vstart have to have enough bits to hold all indicies for minimum SEW and maximum LMUL
        # minimum SEW is 1 byte and maximum LMUL is 8
        self.vstart_bits = log2_int(self.bytes_in_vlen * 8, False)
        self.vvrs_entries_bits = log2_int(self.vvrs_entries, False)

        self.max_lmul = 8
