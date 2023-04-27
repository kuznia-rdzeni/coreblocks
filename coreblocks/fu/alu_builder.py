
from enum import IntFlag, auto
from typing import Any, Sequence, Type
from coreblocks.fu.fu_decoder import DecoderManager
from coreblocks.fu.alu import Alu, ALUComponent
from coreblocks.params import OpType, Funct3, Funct7

class InstExt(IntFlag):
    I = auto()
    ZBA = auto()
    ZBS = auto()

    ANY = I | ZBA | ZBS

class InstTag(IntFlag):
    ADDITION = auto()
    LOGIC = auto()
    COMPARE = auto()
    SHIFT = auto()

    ANY = SHIFT | COMPARE | LOGIC | ADDITION

class Instruction:
    def __init__(self, name: str, encoding: tuple, ext: InstExt, tag: InstTag) -> None:
        self.name = name
        self.ext = ext
        self.encoding = encoding
        self.tag = tag

    def get_encoding(self, fn: Type[IntFlag]):
        if not hasattr(fn, self.name):
            raise Exception()
        
        code = fn[self.name]

        match self.encoding:
            case (a, b): 
                return (code, a, b)
            case (a, b, c): 
                return (code, a, b, c)
            case _:
                raise Exception()
        


instructions = [
    Instruction("ADD", (OpType.ARITHMETIC, Funct3.ADD, Funct7.ADD), InstExt.I, InstTag.ADDITION),
    Instruction("SUB", (OpType.ARITHMETIC, Funct3.ADD, Funct7.SUB), InstExt.I, InstTag.ADDITION),
    Instruction("SLT", (OpType.COMPARE, Funct3.SLT), InstExt.I, InstTag.COMPARE),
    Instruction("SLTU", (OpType.COMPARE, Funct3.SLTU), InstExt.I, InstTag.COMPARE),
    Instruction("XOR", (OpType.LOGIC, Funct3.XOR), InstExt.I, InstTag.LOGIC),
    Instruction("OR", (OpType.LOGIC, Funct3.OR), InstExt.I, InstTag.LOGIC),
    Instruction("AND", (OpType.LOGIC, Funct3.AND), InstExt.I, InstTag.LOGIC),
    Instruction("SLL", (OpType.SHIFT, Funct3.SLL), InstExt.I, InstTag.SHIFT),
    Instruction("SRL", (OpType.SHIFT, Funct3.SR, Funct7.SL), InstExt.I, InstTag.SHIFT),
    Instruction("SRA", (OpType.SHIFT, Funct3.SR, Funct7.SA), InstExt.I, InstTag.SHIFT),
    Instruction("SH1ADD", (OpType.ADDRESS_GENERATION, Funct3.SH1ADD, Funct7.SH1ADD), InstExt.ZBA, InstTag.ADDITION),
    Instruction("SH2ADD", (OpType.ADDRESS_GENERATION, Funct3.SH2ADD, Funct7.SH2ADD), InstExt.ZBA, InstTag.ADDITION),
    Instruction("SH3ADD", (OpType.ADDRESS_GENERATION, Funct3.SH3ADD, Funct7.SH3ADD), InstExt.ZBA, InstTag.ADDITION),
]


class AluBuilder:
    def __init__(self, ext_set: int = InstExt.ANY, tag_set: int = InstTag.ANY) -> None:
        self.ext_set = ext_set
        self.tag_set = tag_set
        self.inst_set = [
            x for x in instructions if x.ext & ext_set != 0 and x.tag & tag_set != 0
        ]

        self.fn = IntFlag("Fn", {
            inst.name: auto() for inst in self.inst_set
        })

        def lookup(fn, name):
            if hasattr(fn, name):
                return fn[name]
            raise Exception()

        self.encoding_set = {
            inst.get_encoding(self.fn) for inst in self.inst_set
        }

        # print(self.encoding_set)
    
    def get_decoder_manger(self):
        fn = self.fn
        inst = self.encoding_set


        class DM(DecoderManager):
            Fn = self.fn

            @classmethod
            def get_instructions(cls) -> Sequence[tuple]:
                return list(inst)

        return DM

    def build_alu(self, gen_params):
        return Alu(gen_params, self.fn)

    def build_component(self):
        return ALUComponent(self.get_decoder_manger())
    

if __name__ == '__main__':
    builder = AluBuilder(InstExt.ANY, InstTag.ANY)



    


    
    



