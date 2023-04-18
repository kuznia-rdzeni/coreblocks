class VectorParameters:
    def __init__(self, *, vlen : int, elen : int):
        self.elen = elen
        self.vlen = vlen

        self.register_bank_count = 4

        accepted_elens = {8,16,32,64}
        if self.elen not in accepted_elens:
            raise ValueError(f"Wrong ELEN value. Got: {self.elen}, expected one of: {accepted_elens}")

        if self.vlen % self.elen !=0:
            raise ValueError(f"Wrong vectors parameters. VLEN should be divisable by ELEN")

        if self.elems_in_vlen%self.v_params.register_bank_count != 0:
            raise ValueError("Number of elements in vector register not divisable by number of banks.")

        self.elems_in_vlen = self.vlen // self.elen
        self.elems_in_bank = self.elems_in_vlen // self.v_params.register_bank_count
