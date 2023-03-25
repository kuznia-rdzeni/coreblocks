from math import floor, log2
from typing import Sequence, Type
from amaranth import *

from coreblocks.params import GenParams, CommonLayouts

from enum import IntFlag


class DecoderManager(Signal):

    Fn: Type[IntFlag]

    @classmethod
    def get_instructions(cls):
        raise NotImplementedError

    optype_dependant = True

    @classmethod
    def get_op_types(cls):
        return {instr[1] for instr in cls.get_instructions()}

    @classmethod
    def get_decoder(cls, gen_params: GenParams):
        return Decoder(gen_params, cls.Fn, cls.get_instructions(), check_optype=cls.optype_dependant)

    def __init__(self, *args, **kwargs):
        super().__init__(self.Fn, *args, **kwargs)


class Decoder(Elaboratable):
    def __init__(self, gen: GenParams, decode_fn: Type[IntFlag], instructions: Sequence[tuple], check_optype: bool):
        layouts = gen.get(CommonLayouts)

        self.exec_fn = Record(layouts.exec_fn)
        self.decode_fn = Signal(decode_fn)
        self.ops = instructions
        self.check_optype = check_optype

    def elaborate(self, platform):
        m = Module()

        for op in self.ops:
            optype_match = self.exec_fn.op_type == op[1] if self.check_optype else 1
            funct3_match = self.exec_fn.funct3 == op[2] if len(op) >= 3 else 1
            funct7_match = self.exec_fn.funct7 == op[3] if len(op) >= 4 else 1

            cond = optype_match & funct3_match & funct7_match

            signal_num = floor(log2(op[0]))

            m.d.comb += self.decode_fn[signal_num].eq(cond)

        return m
