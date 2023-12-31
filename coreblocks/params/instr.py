from abc import abstractmethod, ABC

from amaranth.hdl.ast import ValueCastable
from amaranth import *

from transactron.utils import ValueLike
from coreblocks.params.isa import *


__all__ = [
    "RTypeInstr",
    "ITypeInstr",
    "STypeInstr",
    "BTypeInstr",
    "UTypeInstr",
    "JTypeInstr",
    "IllegalInstr",
    "EBreakInstr",
]


class RISCVInstr(ABC, ValueCastable):
    @abstractmethod
    def pack(self) -> Value:
        pass

    @ValueCastable.lowermethod
    def as_value(self):
        return self.pack()

    def shape(self):
        return self.as_value().shape()


class RTypeInstr(RISCVInstr):
    def __init__(
        self,
        opcode: ValueLike,
        rd: ValueLike,
        funct3: ValueLike,
        rs1: ValueLike,
        rs2: ValueLike,
        funct7: ValueLike,
    ):
        self.opcode = Value.cast(opcode)
        self.rd = Value.cast(rd)
        self.funct3 = Value.cast(funct3)
        self.rs1 = Value.cast(rs1)
        self.rs2 = Value.cast(rs2)
        self.funct7 = Value.cast(funct7)

    def pack(self) -> Value:
        return Cat(C(0b11,2), self.opcode, self.rd, self.funct3, self.rs1, self.rs2, self.funct7)


class ITypeInstr(RISCVInstr):
    def __init__(self, opcode: ValueLike, rd: ValueLike, funct3: ValueLike, rs1: ValueLike, imm: ValueLike):
        self.opcode = Value.cast(opcode)
        self.rd = Value.cast(rd)
        self.funct3 = Value.cast(funct3)
        self.rs1 = Value.cast(rs1)
        self.imm = Value.cast(imm)

    def pack(self) -> Value:
        return Cat(C(0b11,2), self.opcode, self.rd, self.funct3, self.rs1, self.imm)


class STypeInstr(RISCVInstr):
    def __init__(self, opcode: ValueLike, imm: ValueLike, funct3: ValueLike, rs1: ValueLike, rs2: ValueLike):
        self.opcode = Value.cast(opcode)
        self.imm = Value.cast(imm)
        self.funct3 = Value.cast(funct3)
        self.rs1 = Value.cast(rs1)
        self.rs2 = Value.cast(rs2)

    def pack(self) -> Value:
        return Cat(C(0b11,2), self.opcode, self.imm[0:5], self.funct3, self.rs1, self.rs2, self.imm[5:12])


class BTypeInstr(RISCVInstr):
    def __init__(self, opcode: ValueLike, imm: ValueLike, funct3: ValueLike, rs1: ValueLike, rs2: ValueLike):
        self.opcode = Value.cast(opcode)
        self.imm = Value.cast(imm)
        self.funct3 = Value.cast(funct3)
        self.rs1 = Value.cast(rs1)
        self.rs2 = Value.cast(rs2)

    def pack(self) -> Value:
        return Cat(
            C(0b11,2),
            self.opcode,
            self.imm[11],
            self.imm[1:5],
            self.funct3,
            self.rs1,
            self.rs2,
            self.imm[5:11],
            self.imm[12],
        )


class UTypeInstr(RISCVInstr):
    def __init__(self, opcode: ValueLike, rd: ValueLike, imm: ValueLike):
        self.opcode = Value.cast(opcode)
        self.rd = Value.cast(rd)
        self.imm = Value.cast(imm)

    def pack(self) -> Value:
        return Cat(C(0b11,2), self.opcode, self.rd, self.imm[12:])


class JTypeInstr(RISCVInstr):
    def __init__(self, opcode: ValueLike, rd: ValueLike, imm: ValueLike):
        self.opcode = Value.cast(opcode)
        self.rd = Value.cast(rd)
        self.imm = Value.cast(imm)

    def pack(self) -> Value:
        return Cat(C(0b11,2), self.opcode, self.rd, self.imm[12:20], self.imm[11], self.imm[1:11], self.imm[20])


class IllegalInstr(RISCVInstr):
    def __init__(self):
        pass

    def pack(self) -> Value:
        return C(1).replicate(32)  # Instructions with all bits set to 1 are reserved to be illegal.


class EBreakInstr(ITypeInstr):
    def __init__(self):
        super().__init__(
            opcode=Opcode.SYSTEM, rd=Registers.ZERO, funct3=Funct3.PRIV, rs1=Registers.ZERO, imm=Funct12.EBREAK
        )
