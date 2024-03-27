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
from coreblocks.params.isa_params import *
from coreblocks.frontend.decoder.isa import *


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


@dataclass(frozen=True, kw_only=True)
class Field:
    name: str
    base: int | list[int]
    size: int | list[int]

    signed: bool = False
    offset: int = 0
    static_value: Optional[Value] = None

    def get_base(self) -> list[int]:
        if isinstance(self.base, int):
            return [self.base]
        return self.base

    def get_size(self) -> list[int]:
        if isinstance(self.size, int):
            return [self.size]
        return self.size


class RISCVInstr(ABC, ValueCastable):
    field_opcode = Field(name="opcode", base=0, size=7)

    def __init__(self, **kwargs):
        for field in kwargs:
            fname = "field_" + field
            assert fname in dir(self), "Invalid field {} for {}".format(fname, self.__name__)
            setattr(self, field, kwargs[field])

    @classmethod
    def get_fields(cls) -> list[Field]:
        return [getattr(cls, member) for member in dir(cls) if member.startswith("field_")]

    def encode(self) -> int:
        const = Const.cast(self.as_value())
        return const.value  # type: ignore

    def __setattr__(self, key, value):
        fname = "field_{}".format(key)

        if fname not in dir(self):
            super().__setattr__(key, value)
            return

        field = getattr(self, fname)
        if field.static_value is not None:
            raise AttributeError("Can't overwrite the static value of a field.")

        expected_shape = Shape(width=sum(field.get_size()) + field.offset, signed=field.signed)

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

        self.__dict__[key] = field_val

    @ValueCastable.lowermethod
    def as_value(self) -> Value:
        parts: list[tuple[int, Value]] = []

        for field in self.get_fields():
            value: Value = C(0)
            if field.static_value is not None:
                value = field.static_value
            else:
                value = getattr(self, field.name)

            base = field.get_base()
            size = field.get_size()

            offset = field.offset
            for i in range(len(base)):
                parts.append((base[i], value[offset : offset + size[i]]))
                offset += size[i]

        parts.sort()
        return Cat([part[1] for part in parts])

    def shape(self) -> Shape:
        return self.as_value().shape()


class InstructionFunct3Type(RISCVInstr):
    field_funct3 = Field(name="funct3", base=12, size=3)


class InstructionFunct5Type(RISCVInstr):
    field_funct5 = Field(name="funct5", base=27, size=5)


class InstructionFunct7Type(RISCVInstr):
    field_funct7 = Field(name="funct7", base=25, size=7)


class RTypeInstr(InstructionFunct3Type, InstructionFunct7Type):
    field_rd = Field(name="rd", base=7, size=5)
    field_rs1 = Field(name="rs1", base=15, size=5)
    field_rs2 = Field(name="rs2", base=20, size=5)

    def __init__(self, opcode: ValueLike, **kwargs):
        super().__init__(opcode=Cat(C(0b11, 2), opcode), **kwargs)


class ITypeInstr(InstructionFunct3Type):
    field_rd = Field(name="rd", base=7, size=5)
    field_rs1 = Field(name="rs1", base=15, size=5)
    field_imm = Field(name="imm", base=20, size=12, signed=True)

    def __init__(self, opcode: ValueLike, **kwargs):
        super().__init__(opcode=Cat(C(0b11, 2), opcode), **kwargs)


class STypeInstr(InstructionFunct3Type):
    field_rs1 = Field(name="rs1", base=15, size=5)
    field_rs2 = Field(name="rs2", base=20, size=5)
    field_imm = Field(name="imm", base=[7, 25], size=[5, 7], signed=True)

    def __init__(self, opcode: ValueLike, **kwargs):
        super().__init__(opcode=Cat(C(0b11, 2), opcode), **kwargs)


class BTypeInstr(InstructionFunct3Type):
    field_rs1 = Field(name="rs1", base=15, size=5)
    field_rs2 = Field(name="rs2", base=20, size=5)
    field_imm = Field(name="imm", base=[8, 25, 7, 31], size=[4, 6, 1, 1], offset=1, signed=True)

    def __init__(self, opcode: ValueLike, **kwargs):
        super().__init__(opcode=Cat(C(0b11, 2), opcode), **kwargs)


class UTypeInstr(RISCVInstr):
    field_rd = Field(name="rd", base=7, size=5)
    field_imm = Field(name="imm", base=12, size=20, offset=12, signed=False)

    def __init__(self, opcode: ValueLike, **kwargs):
        super().__init__(opcode=Cat(C(0b11, 2), opcode), **kwargs)


class JTypeInstr(RISCVInstr):
    field_rd = Field(name="rd", base=7, size=5)
    field_imm = Field(name="imm", base=[21, 20, 12, 31], size=[10, 1, 8, 1], offset=1, signed=True)

    def __init__(self, opcode: ValueLike, **kwargs):
        super().__init__(opcode=Cat(C(0b11, 2), opcode), **kwargs)


class IllegalInstr(RISCVInstr):
    field_illegal = Field(name="illegal", base=7, size=25, static_value=Cat(1).replicate(25))

    def __init__(self):
        super().__init__(opcode=0b1111111)


class EBreakInstr(ITypeInstr):
    def __init__(self):
        super().__init__(
            opcode=Opcode.SYSTEM, rd=Registers.ZERO, funct3=Funct3.PRIV, rs1=Registers.ZERO, imm=Funct12.EBREAK
        )
