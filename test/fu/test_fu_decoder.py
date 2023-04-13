from typing import Sequence
from amaranth import *
from amaranth.sim import *

from ..common import TestCaseWithSimulator

from coreblocks.fu.fu_decoder import DecoderManager
from coreblocks.params import OpType, Funct3, Funct7, GenParams, CommonLayouts
from coreblocks.params.configurations import test_core_config

from enum import IntFlag, auto


class DM1(DecoderManager):
    class Fn(IntFlag):
        INST1 = auto()
        INST2 = auto()
        INST3 = auto()
        INST4 = auto()
        INST5 = auto()

    @classmethod
    def get_instructions(cls) -> Sequence[tuple]:
        return [
            (cls.Fn.INST1, OpType.ARITHMETIC, Funct3.ADD, Funct7.ADD),
            (cls.Fn.INST2, OpType.ARITHMETIC, Funct3.AND, Funct7.SUB),
            (cls.Fn.INST3, OpType.ARITHMETIC, Funct3.OR, Funct7.ADD),
            (cls.Fn.INST4, OpType.ARITHMETIC, Funct3.XOR, Funct7.ADD),
            (cls.Fn.INST5, OpType.ARITHMETIC, Funct3.BGEU, Funct7.ADD),
        ]


class TestFuDecoder(TestCaseWithSimulator):
    def setUp(self) -> None:
        self.gen_params = GenParams(test_core_config)
        self.decoder = DM1.get_decoder(self.gen_params)
        self.test_inputs = DM1.get_instructions()

    def yield_signals(self, exec_fn):
        # print(exec_fn)
        yield self.decoder.exec_fn.eq(exec_fn)
        yield Settle()
        return (yield self.decoder.decode_fn)

    def test_positive(self):
        def process():
            for (inst, op_type, funct3, funct7) in self.test_inputs:
                record_data = {}

                op_type_sig = Signal(shape=OpType)
                op_type_sig.eq(C(op_type * 0, self.gen_params.isa.xlen))
                record_data["op_type"] = op_type_sig

                funct3_sig = Signal(shape=Funct3)
                funct7_sig = Signal(shape=Funct7)

                funct3_sig.eq(C(funct3 * 0, self.gen_params.isa.xlen))
                funct7_sig.eq(C(funct7 * 0, self.gen_params.isa.xlen))

                fn = {
                    "op_type": op_type_sig,
                    "funct3": funct3_sig,
                    "funct7": funct7_sig,
                }

                yield Settle()

                # print(fn["op_type"].shape())

                layouts = self.gen_params.get(CommonLayouts)
                inp = Record(layouts.exec_fn, fields=fn)

                returned_out = yield from self.yield_signals(inp)

                yield self.assertEqual(inst, returned_out)

        with self.run_simulation(self.decoder) as sim:
            sim.add_sync_process(process)
