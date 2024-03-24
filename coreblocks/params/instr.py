from abc import abstractmethod, ABC

from amaranth.hdl import ValueCastable
from amaranth import *

from transactron.utils import ValueLike
from coreblocks.params.isa_params import *
from coreblocks.frontend.decoder.isa import *


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
        return Cat(C(0b11, 2), self.opcode, self.rd, self.funct3, self.rs1, self.rs2, self.funct7)

    @staticmethod
    def encode(opcode: int, rd: int, funct3: int, rs1: int, rs2: int, funct7: int):
        return int(f"{funct7:07b}{rs2:05b}{rs1:05b}{funct3:03b}{rd:05b}{opcode:05b}11", 2)


class ITypeInstr(RISCVInstr):
    def __init__(self, opcode: ValueLike, rd: ValueLike, funct3: ValueLike, rs1: ValueLike, imm: ValueLike):
        self.opcode = Value.cast(opcode)
        self.rd = Value.cast(rd)
        self.funct3 = Value.cast(funct3)
        self.rs1 = Value.cast(rs1)
        self.imm = Value.cast(imm)

    def pack(self) -> Value:
        return Cat(C(0b11, 2), self.opcode, self.rd, self.funct3, self.rs1, self.imm)

    @staticmethod
    def encode(opcode: int, rd: int, funct3: int, rs1: int, imm: int):
        return int(f"{imm:012b}{rs1:05b}{funct3:03b}{rd:05b}{opcode:05b}11", 2)


class STypeInstr(RISCVInstr):
    def __init__(self, opcode: ValueLike, imm: ValueLike, funct3: ValueLike, rs1: ValueLike, rs2: ValueLike):
        self.opcode = Value.cast(opcode)
        self.imm = Value.cast(imm)
        self.funct3 = Value.cast(funct3)
        self.rs1 = Value.cast(rs1)
        self.rs2 = Value.cast(rs2)

    def pack(self) -> Value:
        return Cat(C(0b11, 2), self.opcode, self.imm[0:5], self.funct3, self.rs1, self.rs2, self.imm[5:12])

    @staticmethod
    def encode(opcode: int, imm: int, funct3: int, rs1: int, rs2: int):
        imm_str = f"{imm:012b}"
        return int(f"{imm_str[5:12]:07b}{rs2:05b}{rs1:05b}{funct3:03b}{imm_str[0:5]:05b}{opcode:05b}11", 2)


class BTypeInstr(RISCVInstr):
    def __init__(self, opcode: ValueLike, imm: ValueLike, funct3: ValueLike, rs1: ValueLike, rs2: ValueLike):
        self.opcode = Value.cast(opcode)
        self.imm = Value.cast(imm)
        self.funct3 = Value.cast(funct3)
        self.rs1 = Value.cast(rs1)
        self.rs2 = Value.cast(rs2)

    def pack(self) -> Value:
        return Cat(
            C(0b11, 2),
            self.opcode,
            self.imm[11],
            self.imm[1:5],
            self.funct3,
            self.rs1,
            self.rs2,
            self.imm[5:11],
            self.imm[12],
        )

    @staticmethod
    def encode(opcode: int, imm: int, funct3: int, rs1: int, rs2: int):
        imm_str = f"{imm:013b}"
        return int(
            f"{imm_str[12]:01b}{imm_str[5:11]:06b}{rs2:05b}{rs1:05b}{funct3:03b}{imm_str[1:5]:04b}"
            + f"{imm_str[11]:01b}{opcode:05b}11",
            2,
        )


class UTypeInstr(RISCVInstr):
    def __init__(self, opcode: ValueLike, rd: ValueLike, imm: ValueLike):
        self.opcode = Value.cast(opcode)
        self.rd = Value.cast(rd)
        self.imm = Value.cast(imm)

    def pack(self) -> Value:
        return Cat(C(0b11, 2), self.opcode, self.rd, self.imm[12:])

    @staticmethod
    def encode(opcode: int, rd: int, imm: int):
        return int(f"{imm:020b}{rd:05b}{opcode:05b}11", 2)


class JTypeInstr(RISCVInstr):
    def __init__(self, opcode: ValueLike, rd: ValueLike, imm: ValueLike):
        self.opcode = Value.cast(opcode)
        self.rd = Value.cast(rd)
        self.imm = Value.cast(imm)

    def pack(self) -> Value:
        return Cat(C(0b11, 2), self.opcode, self.rd, self.imm[12:20], self.imm[11], self.imm[1:11], self.imm[20])

    @staticmethod
    def encode(opcode: int, rd: int, imm: int):
        imm_str = f"{imm:021b}"
        return int(
            f"{imm_str[20]:01b}{imm_str[1:11]:010b}{imm_str[11]:01b}{imm_str[12:20]:08b}{rd:05b}{opcode:05b}11", 2
        )


class IllegalInstr(RISCVInstr):
    def __init__(self):
        pass

    def pack(self) -> Value:
        return C(1).replicate(32)  # Instructions with all bits set to 1 are reserved to be illegal.

    @staticmethod
    def encode(opcode: int, rd: int, imm: int):
        return int("1" * 32, 2)


class EBreakInstr(ITypeInstr):
    def __init__(self):
        super().__init__(
            opcode=Opcode.SYSTEM, rd=Registers.ZERO, funct3=Funct3.PRIV, rs1=Registers.ZERO, imm=Funct12.EBREAK
        )
