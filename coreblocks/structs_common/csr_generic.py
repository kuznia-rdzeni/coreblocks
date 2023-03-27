from amaranth import *

from enum import Enum, auto
from typing import Optional

from coreblocks.params.genparams import GenParams
from coreblocks.params.isa import BitEnum
from coreblocks.structs_common.csr import CSRRegister
from coreblocks.transactions.core import Method, def_method


class CSRAddress(BitEnum, width=12):
    INSTRET = 0xC02
    INSTRETH = 0xC82


class PrivilegeLevel(Enum):
    USER = 0b00
    SUPERVISOR = 0b01
    MACHINE = 0b11
    ILLEGAL = auto()


def get_bits(v: int, upper: int, lower: int):
    return (v >> lower) & ((1 << (upper - lower + 1)) - 1)


def get_access_privilege(csr_addr: int) -> tuple[PrivilegeLevel, bool]:
    read_only = get_bits(csr_addr, 11, 10) == 0b11

    match get_bits(csr_addr, 9, 8):
        case 0b00:
            return (PrivilegeLevel.USER, read_only)
        case 0b01:
            return (PrivilegeLevel.SUPERVISOR, read_only)
        case 0b10:  # Hypervisior CSRs - accessible with VS mode (S with extension)
            return (PrivilegeLevel.SUPERVISOR, read_only)
        case 0b11:
            return (PrivilegeLevel.MACHINE, read_only)

    return (PrivilegeLevel.ILLEGAL, read_only)


class DoubleCounterCSR(Elaboratable):
    def __init__(self, gen_params: GenParams, low_addr: CSRAddress, high_addr: Optional[CSRAddress] = None):
        self.gen_params = gen_params

        self.increment = Method()

        self.register = CSRRegister(low_addr, gen_params)
        self.high_register = (
            CSRRegister(high_addr, gen_params) if gen_params.isa.xlen == 32 and high_addr is not None else None
        )

    def elaborate(self, platform):
        m = Module()

        m.submodules.register = self.register
        if self.high_register is not None:
            m.submodules.high_register = self.high_register

        @def_method(m, self.increment)
        def _():
            register_read = self.register.read(m).data
            self.register.write(m, data=register_read + 1)

            if self.high_register is not None:
                with m.If(register_read == (1 << self.gen_params.isa.xlen) - 1):
                    self.high_register.write(m, data=self.high_register.read(m).data + 1)

        return m
