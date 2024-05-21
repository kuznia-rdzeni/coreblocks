import random
from typing import Sequence, Generator
from amaranth import *
from amaranth.sim import *

from transactron.testing import SimpleTestCircuit, TestCaseWithSimulator

from coreblocks.func_blocks.fu.common.fu_decoder import DecoderManager, Decoder
from coreblocks.arch import OpType, Funct3, Funct7
from coreblocks.params import GenParams
from coreblocks.params.configurations import test_core_config

from enum import IntFlag, auto


class TestFuDecoder(TestCaseWithSimulator):
    def setup_method(self) -> None:
        self.gen_params = GenParams(test_core_config)

    # calculates expected decoder output
    def expected_results(self, instructions: Sequence[tuple], op_type_dependent: bool, inp: dict[str, int]) -> int:
        acc = 0

        for inst in instructions:
            op_type_match = inp["op_type"] == inst[1] if op_type_dependent else True
            funct3_match = inp["funct3"] == inst[2] if len(inst) >= 3 else True
            funct7_match = inp["funct7"] == inst[3] if len(inst) >= 4 else True

            if op_type_match and funct3_match and funct7_match:
                acc |= inst[0]

        return acc

    def handle_signals(self, decoder: Decoder, exec_fn: dict[str, int]) -> Generator:
        yield decoder.exec_fn.op_type.eq(exec_fn["op_type"])
        yield decoder.exec_fn.funct3.eq(exec_fn["funct3"])
        yield decoder.exec_fn.funct7.eq(exec_fn["funct7"])

        yield Settle()

        return (yield decoder.decode_fn)

    def run_test_case(self, decoder_manager: DecoderManager, test_inputs: Sequence[tuple]) -> None:
        instructions = decoder_manager.get_instructions()
        decoder = decoder_manager.get_decoder(self.gen_params)
        op_type_dependent = len(decoder_manager.get_op_types()) != 1

        def process():
            for test_input in test_inputs:
                exec_fn = {
                    "op_type": test_input[1],
                    "funct3": test_input[2] if len(test_input) >= 3 else 0,
                    "funct7": test_input[3] if len(test_input) >= 4 else 0,
                }

                returned = yield from self.handle_signals(decoder, exec_fn)
                expected = self.expected_results(instructions, op_type_dependent, exec_fn)

                assert returned == expected

        test_circuit = SimpleTestCircuit(decoder)

        with self.run_simulation(test_circuit) as sim:
            sim.add_process(process)

    def generate_random_instructions(self) -> Sequence[tuple]:
        random.seed(42)

        return [(0, random.randint(0, 10), random.randint(0, 10), random.randint(0, 10)) for i in range(50)]

    def test_1(self) -> None:
        # same op type
        class DM(DecoderManager):
            class Fn(IntFlag):
                INST1 = auto()
                INST2 = auto()
                INST3 = auto()
                INST4 = auto()
                INST5 = auto()

            def get_instructions(self) -> Sequence[tuple]:
                return [
                    (self.Fn.INST1, OpType.ARITHMETIC, Funct3.ADD, Funct7.ADD),
                    (self.Fn.INST2, OpType.ARITHMETIC, Funct3.AND, Funct7.SUB),
                    (self.Fn.INST3, OpType.ARITHMETIC, Funct3.OR, Funct7.ADD),
                    (self.Fn.INST4, OpType.ARITHMETIC, Funct3.XOR, Funct7.ADD),
                    (self.Fn.INST5, OpType.ARITHMETIC, Funct3.BGEU, Funct7.ADD),
                ]

        decoder_manager = DM()

        test_inputs = list(decoder_manager.get_instructions()) + list(self.generate_random_instructions())

        self.run_test_case(decoder_manager, test_inputs)

    def test_2(self) -> None:
        # same op type, different instruction length
        class DM(DecoderManager):
            class Fn(IntFlag):
                INST1 = auto()
                INST2 = auto()
                INST3 = auto()
                INST4 = auto()
                INST5 = auto()

            def get_instructions(self) -> Sequence[tuple]:
                return [
                    (self.Fn.INST1, OpType.ARITHMETIC, Funct3.ADD, Funct7.ADD),
                    (self.Fn.INST2, OpType.ARITHMETIC, Funct3.AND),
                    (self.Fn.INST3, OpType.ARITHMETIC, Funct3.OR, Funct7.BEXT),
                    (self.Fn.INST4, OpType.ARITHMETIC, Funct3.XOR),
                    (self.Fn.INST5, OpType.ARITHMETIC, Funct3.BGEU, Funct7.BSET),
                ]

        decoder_manager = DM()

        test_inputs = list(decoder_manager.get_instructions()) + list(self.generate_random_instructions())

        self.run_test_case(decoder_manager, test_inputs)

    def test_3(self) -> None:
        # diffecrent op types, different instruction length
        class DM(DecoderManager):
            class Fn(IntFlag):
                INST1 = auto()
                INST2 = auto()
                INST3 = auto()
                INST4 = auto()
                INST5 = auto()

            def get_instructions(self) -> Sequence[tuple]:
                return [
                    (self.Fn.INST1, OpType.AUIPC, Funct3.ADD, Funct7.ADD),
                    (self.Fn.INST2, OpType.MUL, Funct3.AND),
                    (self.Fn.INST3, OpType.ARITHMETIC, Funct3.OR, Funct7.BEXT),
                    (self.Fn.INST4, OpType.COMPARE),
                    (self.Fn.INST5, OpType.ARITHMETIC, Funct3.BGEU, Funct7.BSET),
                ]

        decoder_manager = DM()

        test_inputs = list(decoder_manager.get_instructions()) + list(self.generate_random_instructions())

        self.run_test_case(decoder_manager, test_inputs)
