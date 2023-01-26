from functools import reduce
from operator import or_
from typing import Optional

from amaranth import *

from coreblocks.params import GenParams
from coreblocks.params.isa import *
from coreblocks.utils import AutoDebugSignals

__all__ = ["InstrDecoder"]

from coreblocks.utils import OneHotSwitchDynamic

# Important
#
# In order to add new instructions to be decoded by this decoder assuming they do not required additional
# fields to be extracted you need to add them into `_instructions_by_optype` map, and register new OpType
# into new or existing extension in `optypes_by_extensions` map in `params.isa` module.

# Lists which fields are used by which Instruction's types

_rd_itypes = [InstrType.R, InstrType.I, InstrType.U, InstrType.J]

_rs1_itypes = [InstrType.R, InstrType.I, InstrType.S, InstrType.B]

_rs2_itypes = [InstrType.R, InstrType.S, InstrType.B]

_funct3_itypes = [InstrType.R, InstrType.I, InstrType.S, InstrType.B]

_funct7_itypes = [InstrType.R]


class Encoding:
    """
    Class representing encoding of single RISC-V instruction.

    Attributes
    ----------
    opcode: Opcode
        Opcode of instruction.
    funct3: Optional[Funct3]
        Three bits function identifier. If not exists for instruction then `None`.
    funct7: Optional[Funct7]
        Seven bits function identifier. If not exists for instruction then `None`.
    funct12: Optional[Funct12]
        Twelve bits function identifier. If not exists for instruction then `None`.
    """

    def __init__(
        self,
        opcode: Opcode,
        funct3: Optional[Funct3] = None,
        funct7: Optional[Funct7] = None,
        funct12: Optional[Funct12] = None,
    ):
        self.opcode = opcode
        self.funct3 = funct3
        self.funct7 = funct7
        self.funct12 = funct12


#
# Instructions grouped by Operation types
#

_instructions_by_optype = {
    OpType.ARITHMETIC: [
        Encoding(Opcode.OP_IMM, Funct3.ADD),  # addi
        Encoding(Opcode.OP, Funct3.ADD, Funct7.ADD),  # add
        Encoding(Opcode.OP, Funct3.ADD, Funct7.SUB),  # sub
        Encoding(Opcode.LUI),  # lui
    ],
    OpType.COMPARE: [
        Encoding(Opcode.OP_IMM, Funct3.SLT),  # slti
        Encoding(Opcode.OP_IMM, Funct3.SLTU),  # sltiu
        Encoding(Opcode.OP, Funct3.SLT, Funct7.SLT),  # slt
        Encoding(Opcode.OP, Funct3.SLTU, Funct7.SLT),  # sltu
    ],
    OpType.LOGIC: [
        Encoding(Opcode.OP_IMM, Funct3.XOR),  # xori
        Encoding(Opcode.OP_IMM, Funct3.OR),  # ori
        Encoding(Opcode.OP_IMM, Funct3.AND),  # andi
        Encoding(Opcode.OP, Funct3.XOR, Funct7.XOR),  # xor
        Encoding(Opcode.OP, Funct3.OR, Funct7.OR),  # or
        Encoding(Opcode.OP, Funct3.AND, Funct7.AND),  # and
    ],
    OpType.SHIFT: [
        Encoding(Opcode.OP_IMM, Funct3.SLL, Funct7.SL),  # slli
        Encoding(Opcode.OP_IMM, Funct3.SR, Funct7.SL),  # srli
        Encoding(Opcode.OP_IMM, Funct3.SR, Funct7.SA),  # srai
        Encoding(Opcode.OP, Funct3.SLL, Funct7.SL),  # sll
        Encoding(Opcode.OP, Funct3.SR, Funct7.SL),  # srl
        Encoding(Opcode.OP, Funct3.SR, Funct7.SA),  # sra
    ],
    OpType.AUIPC: [
        Encoding(Opcode.AUIPC),  # auipc
    ],
    OpType.JAL: [
        Encoding(Opcode.JAL),  # jal
    ],
    OpType.JALR: [
        Encoding(Opcode.JALR, Funct3.JALR),  # jalr
    ],
    OpType.BRANCH: [
        Encoding(Opcode.BRANCH, Funct3.BEQ),  # beq
        Encoding(Opcode.BRANCH, Funct3.BNE),  # bne
        Encoding(Opcode.BRANCH, Funct3.BLT),  # blt
        Encoding(Opcode.BRANCH, Funct3.BGE),  # bge
        Encoding(Opcode.BRANCH, Funct3.BLTU),  # bltu
        Encoding(Opcode.BRANCH, Funct3.BGEU),  # bgeu
    ],
    OpType.LOAD: [
        Encoding(Opcode.LOAD, Funct3.B),  # lb
        Encoding(Opcode.LOAD, Funct3.BU),  # lbu
        Encoding(Opcode.LOAD, Funct3.H),  # lh
        Encoding(Opcode.LOAD, Funct3.HU),  # lhu
        Encoding(Opcode.LOAD, Funct3.W),  # lw
    ],
    OpType.STORE: [
        Encoding(Opcode.STORE, Funct3.B),  # sb
        Encoding(Opcode.STORE, Funct3.H),  # sh
        Encoding(Opcode.STORE, Funct3.W),  # sw
    ],
    OpType.FENCE: [
        Encoding(Opcode.MISC_MEM, Funct3.FENCE),  # fence
    ],
    OpType.ECALL: [
        Encoding(Opcode.SYSTEM, Funct3.PRIV, funct12=Funct12.ECALL),  # ecall
    ],
    OpType.EBREAK: [
        Encoding(Opcode.SYSTEM, Funct3.PRIV, funct12=Funct12.EBREAK),  # ebreak
    ],
    OpType.MRET: [
        Encoding(Opcode.SYSTEM, Funct3.PRIV, funct12=Funct12.MRET),  # mret
    ],
    OpType.WFI: [
        Encoding(Opcode.SYSTEM, Funct3.PRIV, funct12=Funct12.WFI),  # wfi
    ],
    OpType.FENCEI: [
        Encoding(Opcode.MISC_MEM, Funct3.FENCEI),  # fence.i
    ],
    OpType.CSR: [
        Encoding(Opcode.SYSTEM, Funct3.CSRRW),  # csrrw
        Encoding(Opcode.SYSTEM, Funct3.CSRRS),  # csrrs
        Encoding(Opcode.SYSTEM, Funct3.CSRRC),  # csrrc
        Encoding(Opcode.SYSTEM, Funct3.CSRRWI),  # csrrwi
        Encoding(Opcode.SYSTEM, Funct3.CSRRSI),  # csrrsi
        Encoding(Opcode.SYSTEM, Funct3.CSRRCI),  # csrrci
    ],
    OpType.MUL: [
        Encoding(Opcode.OP, Funct3.MUL, Funct7.MULDIV),  # mul
        Encoding(Opcode.OP, Funct3.MULH, Funct7.MULDIV),  # mulh
        Encoding(Opcode.OP, Funct3.MULHSU, Funct7.MULDIV),  # mulsu
        Encoding(Opcode.OP, Funct3.MULHU, Funct7.MULDIV),  # mulu
    ],
    OpType.DIV_REM: [
        Encoding(Opcode.OP, Funct3.DIV, Funct7.MULDIV),  # div
        Encoding(Opcode.OP, Funct3.DIVU, Funct7.MULDIV),  # divu
        Encoding(Opcode.OP, Funct3.REM, Funct7.MULDIV),  # rem
        Encoding(Opcode.OP, Funct3.REMU, Funct7.MULDIV),  # remu
    ],
}


class InstrDecoder(Elaboratable, AutoDebugSignals):
    """
    Class performing instruction decoding into elementary components like opcodes, funct3 etc.
    It uses combinatorial connection via its attributes.

    Attributes
    ----------
    instr: Signal(gen.isa.ilen), in
        Instruction to be decoded.
    opcode: Signal(Opcode), out
        Opcode of decoded instruction.
    funct3: Signal(Funct3), out
        Three bits function identifier.
    funct3_v: Signal(1), out
        Signals if decoded instruction has funct3 identifier.
    funct7: Signal(Funct7), out
        Seven bits function identifier.
    funct7_v: Signal(1), out
        Signals if decoded instruction has funct7 identifier.
    funct12: Signal(Funct12), out
        Twelve bits function identifier.
    funct12_v: Signal(1), out
        Signals if decoded instruction has funct12 identifier.
    rs1: Signal(gen.isa.reg_cnt_log), out
        Address of register holding first input value.
    rs1_v: Signal(1), out
        Signal if instruction takes first input value form register.
    rs2: Signal(gen.isa.reg_cnt_log), out
        Address of register holding second input value.
    rs2_v: Signal(1), out
        Signal if instruction takes second input value form register.
    imm: Signal(gen.isa.xlen), out
        Immediate values provided in instruction. If no immediate values were provided then value is 0.
    succ: Signal(FenceTarget), out
        Successor for `FENCE` instructions.
    pred: Signal(FenceTarget), out
        Predecessor for `FENCE` instructions.
    fm: Signal(FenceFm), out
        Fence mode for `FENCE` instructions.
    csr: Signal(gen.isa.csr_alen), out
        Address of Control and Source Register for `CSR` instructions.
    op: Signal(OpType), out
        Operation type of instruction, used to define functional unit to perform this kind of instructions.
    illegal: Signal(1), out
        Signal if decoding of instruction was successful. If instruction do not fit into any supported
        instruction type for selected core generation parameters t then value is 1.
    """

    def __init__(self, gen: GenParams):
        """
        Decoder constructor.

        Parameters
        ----------
        gen: GenParams
            Core generation parameters.
        """
        self.gen = gen

        #
        # Input ports
        #

        self.instr = Signal(gen.isa.ilen)

        #
        # Output ports
        #

        # Opcode and funct
        self.opcode = Signal(Opcode)
        self.funct3 = Signal(Funct3)
        self.funct3_v = Signal()
        self.funct7 = Signal(Funct7)
        self.funct7_v = Signal()
        self.funct12 = Signal(Funct12)
        self.funct12_v = Signal()

        # Destination register
        self.rd = Signal(gen.isa.reg_cnt_log)
        self.rd_v = Signal()

        # First source register
        self.rs1 = Signal(gen.isa.reg_cnt_log)
        self.rs1_v = Signal()

        # Second source register
        self.rs2 = Signal(gen.isa.reg_cnt_log)
        self.rs2_v = Signal()

        # Immediate
        self.imm = Signal(gen.isa.xlen)

        # Fence parameters
        self.succ = Signal(FenceTarget)
        self.pred = Signal(FenceTarget)
        self.fm = Signal(FenceFm)

        # CSR address
        self.csr = Signal(gen.isa.csr_alen)

        # Operation type
        self.op = Signal(OpType)

        # Illegal instruction
        self.illegal = Signal()

    def _extract(self, start: int, sig):
        """
        Method used to for extracting fragment of instruction into provided Signal starting from `start` bit.

        Parameters
        ----------
        start: int
            Start of instruction span to be extracted into.
        sig: Signal
            Signal into which fragment (with length of sig's length) of input will be extracted.

        Returns
        ----------
        Assign
            Assignment of signal.
        """
        return sig.eq(self.instr[start : start + len(sig)])

    def _match(self, encodings: list[Encoding]) -> Value:
        """
        Creates amaranth value of instruction belonging into list of encodings.

        Parameters
        ----------
        encodings: List[Encoding]
            List of encoding to be checked against currently decoding instruction.

        Returns
        ----------
        Value
            Value of instruction having type of encodings in the list.
        """
        return reduce(
            or_,
            map(
                lambda enc: (self.opcode == enc.opcode if enc.opcode is not None else 1)
                & (self.funct3 == enc.funct3 if enc.funct3 is not None else 1)
                & (self.funct7 == enc.funct7 if enc.funct7 is not None else 1)
                & (self.funct12 == enc.funct12 if enc.funct12 is not None else 1)
                & (
                    (self.rd == 0) & (self.rs1 == 0) if enc.opcode == Opcode.SYSTEM and enc.funct3 == Funct3.PRIV else 1
                ),
                encodings,
            ),
        )

    def elaborate(self, platform):
        m = Module()

        # XXX: we always assume the synchronous domain to be present.
        dummy = Signal()
        m.d.sync += dummy.eq(1)

        # Opcode

        opcode = Signal(Opcode)
        m.d.comb += self._extract(2, opcode)

        # Instruction type

        instruction_type = Signal(InstrType)  # format of instruction
        opcode_invalid = Signal()

        with m.Switch(opcode):
            with m.Case(Opcode.OP_IMM, Opcode.JALR, Opcode.LOAD, Opcode.MISC_MEM, Opcode.SYSTEM):
                m.d.comb += instruction_type.eq(InstrType.I)
            with m.Case(Opcode.LUI, Opcode.AUIPC):
                m.d.comb += instruction_type.eq(InstrType.U)
            with m.Case(Opcode.OP):
                m.d.comb += instruction_type.eq(InstrType.R)
            with m.Case(Opcode.JAL):
                m.d.comb += instruction_type.eq(InstrType.J)
            with m.Case(Opcode.BRANCH):
                m.d.comb += instruction_type.eq(InstrType.B)
            with m.Case(Opcode.STORE):
                m.d.comb += instruction_type.eq(InstrType.S)
            with m.Default():
                m.d.comb += opcode_invalid.eq(1)

        # Decode funct

        m.d.comb += self.funct3_v.eq(reduce(or_, (instruction_type == t for t in _funct3_itypes)))
        with m.If(self.funct3_v):
            m.d.comb += self._extract(12, self.funct3)

        m.d.comb += self.funct7_v.eq(
            reduce(or_, (instruction_type == t for t in _funct7_itypes))
            | ((opcode == Opcode.OP_IMM) & ((self.funct3 == Funct3.SLL) | (self.funct3 == Funct3.SR)))
        )
        with m.If(self.funct7_v):
            m.d.comb += self._extract(25, self.funct7)

        m.d.comb += self.funct12_v.eq((opcode == Opcode.SYSTEM) & (self.funct3 == Funct3.PRIV))
        with m.If(self.funct12_v):
            m.d.comb += self._extract(20, self.funct12)

        # Destination and source registers

        m.d.comb += [
            self._extract(7, self.rd),
            self.rd_v.eq(reduce(or_, (instruction_type == t for t in _rd_itypes))),
            self._extract(15, self.rs1),
            self.rs1_v.eq(reduce(or_, (instruction_type == t for t in _rs1_itypes))),
            self._extract(20, self.rs2),
            self.rs2_v.eq(reduce(or_, (instruction_type == t for t in _rs2_itypes))),
        ]

        # Immediate

        iimm12 = Signal(signed(12))
        simm12 = Signal(signed(12))
        bimm13 = Signal(signed(13))
        uimm20 = Signal(unsigned(20))
        jimm20 = Signal(signed(21))
        uimm5 = Signal(unsigned(5))

        instr = self.instr

        m.d.comb += [
            self._extract(20, iimm12),
            simm12.eq(Cat(instr[7:12], instr[25:32])),
            bimm13.eq(Cat(0, instr[8:12], instr[25:31], instr[7], instr[31])),
            self._extract(12, uimm20),
            jimm20.eq(Cat(0, instr[21:31], instr[20], instr[12:20], instr[31])),
            self._extract(15, uimm5),
        ]

        with m.If((self.funct3 == Funct3.SLL) | (self.funct3 == Funct3.SR)):
            m.d.comb += iimm12[5:11].eq(0)

        with m.Switch(instruction_type):
            with m.Case(InstrType.I):
                m.d.comb += self.imm.eq(iimm12)
            with m.Case(InstrType.S):
                m.d.comb += self.imm.eq(simm12)
            with m.Case(InstrType.B):
                m.d.comb += self.imm.eq(bimm13)
            with m.Case(InstrType.U):
                m.d.comb += self.imm.eq(uimm20 << (self.gen.isa.xlen - 20))
            with m.Case(InstrType.J):
                m.d.comb += self.imm.eq(jimm20)

        # Fence parameters

        m.d.comb += [
            self._extract(20, self.succ),
            self._extract(24, self.pred),
            self._extract(28, self.fm),
        ]

        # CSR address

        m.d.comb += self._extract(20, self.csr)

        # Operation type

        extensions = self.gen.isa.extensions
        op_type_mask = Signal(len(OpType) - 1)

        first_valid_optype = OpType.UNKNOWN.value + 1  # value of first OpType which is not UNKNOWN

        for ext, optypes in optypes_by_extensions.items():
            if extensions & ext:
                for optype in optypes:
                    list_of_encodings = _instructions_by_optype[optype]
                    m.d.comb += op_type_mask[optype.value - first_valid_optype].eq(self._match(list_of_encodings))

        for i in OneHotSwitchDynamic(m, op_type_mask, default=True):
            if i is not None:
                m.d.comb += self.op.eq(i + first_valid_optype)
            else:  # default case
                m.d.comb += self.op.eq(OpType.UNKNOWN)

        # Instruction simplification

        # lui rd, imm -> addi rd, x0, (imm << 12)
        with m.If(opcode == Opcode.LUI):
            m.d.comb += [
                self.opcode.eq(Opcode.OP_IMM),
                self.funct3.eq(Funct3.ADD),
                self.funct3_v.eq(1),
                self.rs1.eq(0),
            ]
        with m.Else():
            m.d.comb += self.opcode.eq(opcode)

        # Immediate correction

        with m.If(self.op == OpType.CSR):
            m.d.comb += self.imm.eq(uimm5)

        # Illegal instruction detection

        m.d.comb += self.illegal.eq(opcode_invalid | (self.op == OpType.UNKNOWN))

        return m
