from coreblocks.params.vector_params import VectorParameters

class RegisterLayouts:
    def __init__(self, gen_params: GenParams, v_params : VectorParameters):
        self.read_resp = [
            ("data", v_params.elen)
        ]
