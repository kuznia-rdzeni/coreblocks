from amaranth import *
from ..transactions import Method, Transaction
from ..params import GenParams
from .decoder import InstrDecoder


class Decode(Elaboratable):
    """
    Simple decode unit. This is a transactional interface which instantiates a
    submodule `InstrDecoder`. This `InstrDecoder` makes actual decoding in
    a combinatorial manner.

    """

    def __init__(self, gen_params: GenParams, get_raw: Method, push_decoded: Method) -> None:
        """
        Parameters
        ----------
        gen_params : GenParams
            Instance of GenParams with parameters which should be used to generate
            fetch unit.
        get_raw : Method
            Method which is invoked to get raw instruction from previous step
            (e.g. from fetch unit) it uses `FetchLayout`.
        push_decoded : Method
            Method which is invoked to send decoded data to the next step.
            It has layout as described by `DecodeLayouts`.
        """
        self.gp = gen_params
        self.get_raw = get_raw
        self.push_decoded = push_decoded

    def elaborate(self, platform) -> Module:
        m = Module()

        m.submodules.instr_decoder = instr_decoder = InstrDecoder(self.gp)

        with Transaction().body(m):
            raw = self.get_raw(m)
            m.d.comb += instr_decoder.instr.eq(raw.data)

            self.push_decoded(
                m,
                {
                    "opcode": instr_decoder.opcode,
                    "illegal": instr_decoder.illegal,
                    "exec_fn": {
                        "op_type": instr_decoder.op,
                        "funct3": instr_decoder.funct3,
                        "funct7": instr_decoder.funct7,
                    },
                    "regs_l": {
                        "rl_dst": instr_decoder.rd,
                        "rl_dst_v": instr_decoder.rd_v,
                        "rl_s1": instr_decoder.rs1,
                        "rl_s1_v": instr_decoder.rs1_v,
                        "rl_s2": instr_decoder.rs2,
                        "rl_s2_v": instr_decoder.rs2_v,
                    },
                    "imm": instr_decoder.imm,
                    "csr": instr_decoder.csr,
                    "pc": raw.pc,
                },
            )

        return m
