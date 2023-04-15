from typing import Sequence, Type
from amaranth import *

from coreblocks.params import GenParams, CommonLayouts

from enum import IntFlag

from coreblocks.params.optypes import OpType


class Decoder(Elaboratable):
    """
    Module responsible for instruction decoding.

    Attributes
    ----------
    decode_fn: Signal
    exec_fn: Record
    """

    def __init__(self, gen_params: GenParams, decode_fn: Type[IntFlag], ops: Sequence[tuple], check_optype: bool):
        layouts = gen_params.get(CommonLayouts)

        self.exec_fn = Record(layouts.exec_fn)
        self.decode_fn = Signal(decode_fn)
        self.ops = ops
        self.check_optype = check_optype

    def elaborate(self, platform):
        m = Module()

        for op in self.ops:
            optype_match = self.exec_fn.op_type == op[1] if self.check_optype else 1
            funct3_match = self.exec_fn.funct3 == op[2] if len(op) >= 3 else 1
            funct7_match = self.exec_fn.funct7 == op[3] if len(op) >= 4 else 1

            cond = optype_match & funct3_match & funct7_match

            signal_num = op[0].bit_length() - 1

            m.d.comb += self.decode_fn[signal_num].eq(cond)

        # dummy signal to enable time domain while testing
        dummy = Signal()
        m.d.sync += dummy.eq(1)

        return m


class DecoderManager:
    """
    Class responsible for instruction management.
    """

    """
    Type[IntFlag]

    Enumeration of instructions implemented in given functional unit.
    """
    Fn: Type[IntFlag]

    """
    Method providing list of valid instruction.

    Returns
    -------
    return : Sequence[tuple]
        List of implemented instructions, each following format:
        (IntFlag, OpType, Funct3 (optional), Funct7 (optional))

    """

    @classmethod
    def get_instructions(cls) -> Sequence[tuple]:
        raise NotImplementedError

    """
    Method returning op types from listed instructions.

    Returns
    -------
    return : set[OpType]
        List of OpTypes.
    """

    @classmethod
    def get_op_types(cls) -> set[OpType]:
        return {instr[1] for instr in cls.get_instructions()}

    """
    Method returning auto generated instruction decoder.

    Parameters
    ----------
    gen_params: GenParams
        Generation parameters passed to a decoder contructor.

    Returns
    -------
    return : set[OpType]
        List of OpTypes.
    """

    @classmethod
    def get_decoder(cls, gen_params: GenParams) -> Decoder:
        # check how many different op types are there
        op_types = cls.get_op_types()
        multiple_op_types = len(op_types) > 1

        # if multiple op types detected, request op_type check in decoder
        return Decoder(gen_params, cls.Fn, cls.get_instructions(), check_optype=multiple_op_types)

    """
    Method returning Signal Object for decoder, called function in FU blocks

    Returns
    -------
    return : Value
        Signal object.
    """

    @classmethod
    def get_function(cls) -> Value:
        return Signal(cls.Fn)
