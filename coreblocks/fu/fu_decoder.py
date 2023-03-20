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
    def get_instrutions(cls):
        return []

    @classmethod
    def get_intruction_enum(cls):
        return cls.Fn

    @classmethod
    def get_op_types(cls):
        istr = cls.get_instrutions()

        op_types = set()

        for inst in istr:
            op_types.add(inst[1])

        return op_types

    @classmethod
    def get_decoder(cls, gen):
        return Decoder(gen, cls.Fn, cls.get_instrutions())

    def __init__(self, *args, **kwargs):
        super().__init__(self.Fn, *args, **kwargs)


class Decoder(Elaboratable):
    def __init__(self, gen: GenParams, decode_fn, instructions):
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
