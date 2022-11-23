from amaranth import *
from ..transactions import Method, Transaction
from ..params import GenParams, DecodeLayouts
from .decoder import InstrDecoder


class Decode(Elaboratable):
    def __init__(self, gen_params: GenParams, get_raw: Method, push_decoded: Method) -> None:
        """
        Simple decode unit. This is a transactional interface which instantiates a
        submodule `InstrDecoder`. This `InstrDecoder` makes actual decoding in
        a combinatorial manner.

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

            decoded = Record(self.gp.get(DecodeLayouts).decoded_instr)

            m.d.comb += decoded.opcode.eq(instr_decoder.opcode)
            m.d.comb += decoded.illegal.eq(instr_decoder.illegal)

            exec_fn = decoded.exec_fn
            m.d.comb += exec_fn.op_type.eq(instr_decoder.op)
            m.d.comb += exec_fn.funct3.eq(instr_decoder.funct3)
            m.d.comb += exec_fn.funct7.eq(instr_decoder.funct7)

            regs = decoded.regs_l
            m.d.comb += regs.rl_dst.eq(instr_decoder.rd)
            m.d.comb += regs.rl_dst_v.eq(instr_decoder.rd_v)
            m.d.comb += regs.rl_s1.eq(instr_decoder.rs1)
            m.d.comb += regs.rl_s1_v.eq(instr_decoder.rs1_v)
            m.d.comb += regs.rl_s2.eq(instr_decoder.rs2)
            m.d.comb += regs.rl_s2_v.eq(instr_decoder.rs2_v)

            m.d.comb += decoded.imm.eq(instr_decoder.imm)

            self.push_decoded(m, decoded)

        return m
