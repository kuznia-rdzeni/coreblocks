from amaranth import *

from coreblocks.transactions import *
from coreblocks.transactions.lib import *

from coreblocks.params import *

from enum import IntFlag


class DecoderManager(Signal):
    @unique
    class Fn(IntFlag):
        pass

    @classmethod
    def get_instructions(cls):
        raise NotImplementedError

    @classmethod
    def get_op_types(cls):
        return {instr[1] for instr in cls.get_instructions()}

    @classmethod
    def get_decoder(cls, gen_params: GenParams):
        return Decoder(gen_params, cls.Fn, cls.get_instructions())

    def __init__(self, *args, **kwargs):
        super().__init__(self.Fn, *args, **kwargs)


class Decoder(Elaboratable):
    def __init__(self, gen: GenParams, decode_fn: IntFlag, instructions: Array[tuple]):
        layouts = gen.get(CommonLayouts)

        self.exec_fn = Record(layouts.exec_fn)
        self.decode_fn = Signal(decode_fn)
        self.ops = instructions

    def elaborate(self, platform):
        m = Module()

        for op in self.ops:
            cond = (self.exec_fn.op_type == op[1]) & (self.exec_fn.funct3 == op[2])
            if len(op) == 4:
                cond = cond & (self.exec_fn.funct7 == op[3])

            with m.If(cond):
                m.d.comb += self.decode_fn.eq(op[0])

        return m
