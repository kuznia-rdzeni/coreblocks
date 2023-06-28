from amaranth import *
from ..transactions import Method, Transaction, TModule
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

    def elaborate(self, platform):
        m = TModule()

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
                        "op_type": instr_decoder.optype,
                        # imm muxing in FUs depend on unused functs set to 0
                        "funct3": Mux(instr_decoder.funct3_v, instr_decoder.funct3, 0),
                        "funct7": Mux(instr_decoder.funct7_v, instr_decoder.funct7, 0),
                    },
                    "regs_l": {
                        # read/writes to phys reg 0 make no effect
                        "rl_dst": Mux(instr_decoder.rd_v, instr_decoder.rd, 0),
                        "rl_dst_rf": Mux(instr_decoder.rd_v, instr_decoder.rd_rf, 0),
                        "rl_s1": Mux(instr_decoder.rs1_v, instr_decoder.rs1, 0),
                        "rl_s1_rf": Mux(instr_decoder.rs1_v, instr_decoder.rs1_rf, 0),
                        "rl_s2": Mux(instr_decoder.rs2_v, instr_decoder.rs2, 0),
                        "rl_s2_rf": Mux(instr_decoder.rs2_v, instr_decoder.rs2_rf, 0),
                    },
                    "imm": instr_decoder.imm,
                    "imm2": instr_decoder.imm2,
                    "pc": raw.pc,
                },
            )

        return m
