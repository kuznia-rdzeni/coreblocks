"""

Based on riscv-python-model by Stefan Wallentowitz
https://github.com/wallento/riscv-python-model
"""

from dataclasses import dataclass
from abc import ABC
from enum import Enum
from typing import Optional

from amaranth.hdl import ValueCastable
from amaranth import *

from transactron.utils import ValueLike
from coreblocks.arch import Opcode, Registers, Funct3, Funct12


__all__ = [
    "RISCVInstr",
    "RTypeInstr",
    "ITypeInstr",
    "STypeInstr",
    "BTypeInstr",
    "UTypeInstr",
    "JTypeInstr",
    "IllegalInstr",
    "EBreakInstr",
]


@dataclass(kw_only=True)
class Field:
    """Information about a field in a RISC-V instruction.

    Attributes
    ----------
    base: int | list[int]
        A bit position (or a list of positions) where this field (or parts of the field)
        would map in the instruction.
    size: int | list[int]
        Size (or sizes of the parts) of the field
    signed: bool
        Whether this field encodes a signed value.
    offset: int
        How many bits of this field should be skipped when encoding the instruction.
        For example, the immediate of the jump instruction always skips the least
        significant bit. This only affects encoding procedures, so externally (for example
        when creating an instance of a instruction) full-size values should be always used.
    static_value: Optional[Value]
        Whether the field should have a static value for a given type of an instruction.
    """

    base: int | list[int]
    size: int | list[int]

    signed: bool = False
    offset: int = 0
    static_value: Optional[Value] = None

    _name: str = ""

    def bases(self) -> list[int]:
        return [self.base] if isinstance(self.base, int) else self.base

    def sizes(self) -> list[int]:
        return [self.size] if isinstance(self.size, int) else self.size

    def shape(self) -> Shape:
        return Shape(width=sum(self.sizes()) + self.offset, signed=self.signed)

    def __set_name__(self, owner, name):
        self._name = name

    def __get__(self, obj, objtype=None) -> Value:
        if self.static_value is not None:
            return self.static_value

        return obj.__dict__.get(self._name, C(0, self.shape()))

    def __set__(self, obj, value) -> None:
        if self.static_value is not None:
            raise AttributeError("Can't overwrite the static value of a field.")

        expected_shape = self.shape()

        field_val: Value = C(0)
        if isinstance(value, Enum):
            field_val = Const(value.value, expected_shape)
        elif isinstance(value, int):
            field_val = Const(value, expected_shape)
        else:
            field_val = Value.cast(value)

            if field_val.shape().width != expected_shape.width:
                raise AttributeError(
                    f"Expected width of the value: {expected_shape.width}, given: {field_val.shape().width}"
                )
            if field_val.shape().signed and not expected_shape.signed:
                raise AttributeError(
                    f"Expected signedness of the value: {expected_shape.signed}, given: {field_val.shape().signed}"
                )

        obj.__dict__[self._name] = field_val

    def get_parts(self, value: Value) -> list[Value]:
        base = self.bases()
        size = self.sizes()
        offset = self.offset

        ret: list[Value] = []
        for i in range(len(base)):
            ret.append(value[offset : offset + size[i]])
            offset += size[i]

        return ret


def _get_fields(cls: type) -> list[Field]:
    fields = [cls.__dict__[member] for member in vars(cls) if isinstance(cls.__dict__[member], Field)]
    field_ids = set([id(field) for field in fields])
    for base in cls.__bases__:
        for field in _get_fields(base):
            if id(field) in field_ids:
                continue
            fields.append(field)
            field_ids.add(id(field))

    return fields


class RISCVInstr(ABC, ValueCastable):
    opcode = Field(base=0, size=7)

    def __init__(self, opcode: Opcode):
        self.opcode = Cat(C(0b11, 2), opcode)

    def encode(self) -> int:
        const = Const.cast(self.as_value())
        return const.value  # type: ignore

    @ValueCastable.lowermethod
    def as_value(self) -> Value:
        parts: list[tuple[int, Value]] = []

        for field in _get_fields(type(self)):
            value = field.__get__(self, type(self))
            parts += zip(field.bases(), field.get_parts(value))

        parts.sort()
        return Cat([part[1] for part in parts])

    def shape(self) -> Shape:
        return self.as_value().shape()


class InstructionFunct3Type(RISCVInstr):
    funct3 = Field(base=12, size=3)


class InstructionFunct7Type(RISCVInstr):
    funct7 = Field(base=25, size=7)


class RTypeInstr(InstructionFunct3Type, InstructionFunct7Type):
    rd = Field(base=7, size=5)
    rs1 = Field(base=15, size=5)
    rs2 = Field(base=20, size=5)

    def __init__(
        self, opcode: Opcode, funct3: ValueLike, funct7: ValueLike, rd: ValueLike, rs1: ValueLike, rs2: ValueLike
    ):
        super().__init__(opcode)
        self.funct3 = funct3
        self.funct7 = funct7
        self.rd = rd
        self.rs1 = rs1
        self.rs2 = rs2


class ITypeInstr(InstructionFunct3Type):
    rd = Field(base=7, size=5)
    rs1 = Field(base=15, size=5)
    imm = Field(base=20, size=12, signed=True)

    def __init__(self, opcode: Opcode, funct3: ValueLike, rd: ValueLike, rs1: ValueLike, imm: ValueLike):
        super().__init__(opcode)
        self.funct3 = funct3
        self.rd = rd
        self.rs1 = rs1
        self.imm = imm


class STypeInstr(InstructionFunct3Type):
    rs1 = Field(base=15, size=5)
    rs2 = Field(base=20, size=5)
    imm = Field(base=[7, 25], size=[5, 7], signed=True)

    def __init__(self, opcode: Opcode, funct3: ValueLike, rs1: ValueLike, rs2: ValueLike, imm: ValueLike):
        super().__init__(opcode)
        self.funct3 = funct3
        self.rs1 = rs1
        self.rs2 = rs2
        self.imm = imm


class BTypeInstr(InstructionFunct3Type):
    rs1 = Field(base=15, size=5)
    rs2 = Field(base=20, size=5)
    imm = Field(base=[8, 25, 7, 31], size=[4, 6, 1, 1], offset=1, signed=True)

    def __init__(self, opcode: Opcode, funct3: ValueLike, rs1: ValueLike, rs2: ValueLike, imm: ValueLike):
        super().__init__(opcode)
        self.funct3 = funct3
        self.rs1 = rs1
        self.rs2 = rs2
        self.imm = imm


class UTypeInstr(RISCVInstr):
    rd = Field(base=7, size=5)
    imm = Field(base=12, size=20, offset=12, signed=True)

    def __init__(self, opcode: Opcode, rd: ValueLike, imm: ValueLike):
        super().__init__(opcode)
        self.rd = rd
        self.imm = imm


class JTypeInstr(RISCVInstr):
    rd = Field(base=7, size=5)
    imm = Field(base=[21, 20, 12, 31], size=[10, 1, 8, 1], offset=1, signed=True)

    def __init__(self, opcode: Opcode, rd: ValueLike, imm: ValueLike):
        super().__init__(opcode)
        self.rd = rd
        self.imm = imm


class IllegalInstr(RISCVInstr):
    illegal = Field(base=7, size=25, static_value=Cat(1).replicate(25))

    def __init__(self):
        super().__init__(opcode=Opcode.RESERVED)


class EBreakInstr(ITypeInstr):
    def __init__(self):
        super().__init__(
            opcode=Opcode.SYSTEM, rd=Registers.ZERO, funct3=Funct3.PRIV, rs1=Registers.ZERO, imm=Funct12.EBREAK
        )
