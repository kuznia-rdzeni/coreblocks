from typing import Sequence, Type
from amaranth import *

from coreblocks.params import GenParams
from coreblocks.interface.layouts import CommonLayoutFields

from enum import IntFlag

from coreblocks.arch.optypes import OpType


class Decoder(Elaboratable):
    """
    Module responsible for instruction decoding.

    Attributes
    ----------
    decode_fn: Signal
    exec_fn: View
    """

    def __init__(self, gen_params: GenParams, decode_fn: Type[IntFlag], ops: Sequence[tuple], check_optype: bool):
        layouts = gen_params.get(CommonLayoutFields)

        self.exec_fn = Signal(layouts.exec_fn_layout)
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

        return m


class DecoderManager:
    """Class responsible for instruction management."""

    Fn: Type[IntFlag]
    """Enumeration of instructions implemented in given functional unit."""

    def get_instructions(self) -> Sequence[tuple]:
        """Method providing list of valid instruction.

        Returns
        -------
        return : Sequence[tuple]
            List of implemented instructions, each following format:
            (IntFlag, OpType, Funct3 (optional), Funct7 (optional))

        """
        raise NotImplementedError

    def get_op_types(self) -> set[OpType]:
        """Method returning op types from listed instructions.

        Returns
        -------
        return : set[OpType]
            List of OpTypes.
        """
        return {instr[1] for instr in self.get_instructions()}

    def get_decoder(self, gen_params: GenParams) -> Decoder:
        """Method returning auto generated instruction decoder.

        Parameters
        ----------
        gen_params: GenParams
            Generation parameters passed to a decoder contructor.

        Returns
        -------
        return : Decoder
            Instance of Decoder class.
        """
        # check how many different op types are there
        op_types = self.get_op_types()
        multiple_op_types = len(op_types) > 1

        # if multiple op types detected, request op_type check in decoder
        return Decoder(gen_params, self.Fn, self.get_instructions(), check_optype=multiple_op_types)

    def get_function(self) -> Value:
        """Method returning Signal Object for decoder, called function in FU blocks

        Returns
        -------
        return : Value
            Signal object.
        """
        return Signal(self.Fn)
