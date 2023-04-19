from coreblocks.params.vector_params import VectorParameters

class RegisterLayouts:
    def __init__(self, gen_params: GenParams, v_params : VectorParameters):
        self.read_resp = [
            ("data", v_params.elen)
        ]

        self.write= [
            ("addr", range(v_params.elems_in_bank)),
            ("data", v_params.elen),
            ("mask", v_params.bytes_in_elen)
                ]
