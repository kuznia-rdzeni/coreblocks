from dataclasses import KW_ONLY, dataclass
from functools import reduce
from operator import or_
from typing import Optional

from amaranth import *

from coreblocks.params import *

__all__ = ["InstrDecoder"]

# Important
#
# In order to add new instructions to be decoded by this decoder assuming they do not required additional
# fields to be extracted you need to add them into `_instructions_by_optype` map, and register new OpType
# into new or existing extension in `optypes_by_extensions` map in `params.optypes` module.

# Lists which fields are used by which Instruction's types

_rd_itypes = [InstrType.R, InstrType.I, InstrType.U, InstrType.J]

_rs1_itypes = [InstrType.R, InstrType.I, InstrType.S, InstrType.B]

_rs2_itypes = [InstrType.R, InstrType.S, InstrType.B]


@dataclass(frozen=True)
class Encoding:
    """
    Class representing encoding of single RISC-V instruction.

    Parameters
    ----------
    opcode: Opcode
        Opcode of instruction.
    funct3: Optional[Funct3]
        Three bits function identifier. If not exists for instruction then `None`.
    funct7: Optional[Funct7]
        Seven bits function identifier. If not exists for instruction then `None`.
    funct12: Optional[Funct12]
        Twelve bits function identifier. If not exists for instruction then `None`.
    instr_type_override: Optional[InstrType]
        Specify `InstrType` used for decoding of register and immediate for single opcode.
        If set to `None` optype is determined from instrustion opcode, which is almost always correct.
    rd_zero: bool
        `rd` field is specifed as constant zero in instruction encoding. Other fields are decoded
        accordingly to `InstrType`. Default is False.
    rs1_zero: bool
        `rs1` field is specifed as constant zero in instruction encoding. Other fields are decoded
        accordingly to `InstrType`. Default is False.
    """

    opcode: Opcode
    funct3: Optional[Funct3] = None
    funct7: Optional[Funct7] = None
    funct12: Optional[Funct12] = None
    _ = KW_ONLY
    instr_type_override: Optional[InstrType] = None
    rd_zero: bool = False
    rs1_zero: bool = False


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
        Encoding(Opcode.SYSTEM, Funct3.PRIV, funct12=Funct12.ECALL, rd_zero=True, rs1_zero=True),  # ecall
    ],
    OpType.EBREAK: [
        Encoding(Opcode.SYSTEM, Funct3.PRIV, funct12=Funct12.EBREAK, rd_zero=True, rs1_zero=True),  # ebreak
    ],
    OpType.MRET: [
        Encoding(Opcode.SYSTEM, Funct3.PRIV, funct12=Funct12.MRET, rd_zero=True, rs1_zero=True),  # mret
    ],
    OpType.WFI: [
        Encoding(Opcode.SYSTEM, Funct3.PRIV, funct12=Funct12.WFI, rd_zero=True, rs1_zero=True),  # wfi
    ],
    OpType.FENCEI: [
        Encoding(Opcode.MISC_MEM, Funct3.FENCEI),  # fence.i
    ],
    OpType.CSR_REG: [
        Encoding(Opcode.SYSTEM, Funct3.CSRRW),  # csrrw
        Encoding(Opcode.SYSTEM, Funct3.CSRRS),  # csrrs
        Encoding(Opcode.SYSTEM, Funct3.CSRRC),  # csrrc
    ],
    OpType.CSR_IMM: [
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
    OpType.SINGLE_BIT_MANIPULATION: [
        Encoding(Opcode.OP, Funct3.BCLR, Funct7.BCLR),  # bclr
        Encoding(Opcode.OP_IMM, Funct3.BCLR, Funct7.BCLR),  # bclri
        Encoding(Opcode.OP, Funct3.BEXT, Funct7.BEXT),  # bext
        Encoding(Opcode.OP_IMM, Funct3.BEXT, Funct7.BEXT),  # bexti
        Encoding(Opcode.OP, Funct3.BSET, Funct7.BSET),  # bset
        Encoding(Opcode.OP_IMM, Funct3.BSET, Funct7.BSET),  # bseti
        Encoding(Opcode.OP, Funct3.BINV, Funct7.BINV),  # binv
        Encoding(Opcode.OP_IMM, Funct3.BINV, Funct7.BINV),  # binvi
    ],
    OpType.ADDRESS_GENERATION: [
        Encoding(Opcode.OP, Funct3.SH1ADD, Funct7.SH1ADD),
        Encoding(Opcode.OP, Funct3.SH2ADD, Funct7.SH2ADD),
        Encoding(Opcode.OP, Funct3.SH3ADD, Funct7.SH3ADD),
    ],
    OpType.BIT_MANIPULATION: [
        Encoding(Opcode.OP, Funct3.ANDN, Funct7.ANDN),
        Encoding(Opcode.OP, Funct3.MAX, Funct7.MAX),
        Encoding(Opcode.OP, Funct3.MAXU, Funct7.MAX),
        Encoding(Opcode.OP, Funct3.MIN, Funct7.MIN),
        Encoding(Opcode.OP, Funct3.MINU, Funct7.MIN),
        Encoding(Opcode.OP, Funct3.ORN, Funct7.ORN),
        Encoding(Opcode.OP, Funct3.ROL, Funct7.ROL),
        Encoding(Opcode.OP, Funct3.ROR, Funct7.ROR),
        Encoding(Opcode.OP_IMM, Funct3.ROR, Funct7.ROR),
        Encoding(Opcode.OP, Funct3.XNOR, Funct7.XNOR),
    ],
    OpType.UNARY_BIT_MANIPULATION_1: [
        Encoding(Opcode.OP_IMM, Funct3.ORCB, funct12=Funct12.ORCB),
        Encoding(Opcode.OP_IMM, Funct3.REV8, funct12=Funct12.REV8_32),
        Encoding(Opcode.OP_IMM, Funct3.SEXTB, funct12=Funct12.SEXTB),
        Encoding(Opcode.OP, Funct3.ZEXTH, funct12=Funct12.ZEXTH),
    ],
    # Instructions SEXTH, SEXTHB, CPOP, CLZ and CTZ  cannot be distiguished by their Funct7 code
    OpType.UNARY_BIT_MANIPULATION_2: [
        Encoding(Opcode.OP_IMM, Funct3.SEXTH, funct12=Funct12.SEXTH),
    ],
    OpType.UNARY_BIT_MANIPULATION_3: [
        Encoding(Opcode.OP_IMM, Funct3.CLZ, funct12=Funct12.CLZ),
    ],
    OpType.UNARY_BIT_MANIPULATION_4: [
        Encoding(Opcode.OP_IMM, Funct3.CTZ, funct12=Funct12.CTZ),
    ],
    OpType.UNARY_BIT_MANIPULATION_5: [
        Encoding(Opcode.OP_IMM, Funct3.CPOP, funct12=Funct12.CPOP),
    ],
    OpType.CLMUL: [
        Encoding(Opcode.OP, Funct3.CLMUL, Funct7.CLMUL),
        Encoding(Opcode.OP, Funct3.CLMULH, Funct7.CLMUL),
        Encoding(Opcode.OP, Funct3.CLMULR, Funct7.CLMUL),
    ],
    OpType.SRET: [
        Encoding(Opcode.SYSTEM, Funct3.PRIV, funct12=Funct12.SRET, rd_zero=True, rs1_zero=True),  # sret
    ],
    OpType.SFENCEVMA: [
        Encoding(
            Opcode.SYSTEM, Funct3.PRIV, Funct7.SFENCEVMA, rd_zero=True, instr_type_override=InstrType.R
        ),  # sfence.vma
    ],
}


class InstrDecoder(Elaboratable):
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
    rd: Signal(gen.isa.reg_cnt_log), out
        Address of register to write instruction result.
    rd_v: Signal(1), out
        Signal if instruction writes to register.
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
    optype: Signal(OpType), out
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
        self.optype = Signal(OpType)

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

    def elaborate(self, platform):
        m = Module()

        extensions = self.gen.isa.extensions
        supported_encodings: set[Encoding] = set()
        encoding_to_optype: dict[Encoding, OpType] = dict()
        for ext, optypes in optypes_by_extensions.items():
            if extensions & ext:
                for optype in optypes:
                    for encoding in _instructions_by_optype[optype]:
                        supported_encodings.add(encoding)
                        encoding_to_optype[encoding] = optype

        # Opcode

        opcode = Signal(Opcode)
        m.d.comb += self._extract(2, opcode)

        # Instruction type

        instruction_type = Signal(InstrType)  # format of instruction

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

        # Decode and match instruction encoding

        m.d.comb += [
            self._extract(12, self.funct3),
            self._extract(25, self.funct7),
            self._extract(20, self.funct12),
        ]

        m.d.comb += [
            self._extract(7, self.rd),
            self._extract(15, self.rs1),
            self._extract(20, self.rs2),
        ]

        rd_invalid = Signal()
        rs1_invalid = Signal()

        m.d.comb += self.optype.eq(OpType.UNKNOWN)

        for enc in supported_encodings:
            with m.If(
                (opcode == enc.opcode if enc.opcode is not None else 1)
                & (self.funct3 == enc.funct3 if enc.funct3 is not None else 1)
                & (self.funct7 == enc.funct7 if enc.funct7 is not None else 1)
                & (self.funct12 == enc.funct12 if enc.funct12 is not None else 1)
                & (self.rd == 0 if enc.rd_zero else 1)
                & (self.rs1 == 0 if enc.rs1_zero else 1)
            ):
                m.d.comb += self.optype.eq(encoding_to_optype[enc])

                if enc.instr_type_override is not None:
                    m.d.comb += instruction_type.eq(enc.instr_type_override)

                m.d.comb += rd_invalid.eq(enc.rd_zero)
                m.d.comb += rs1_invalid.eq(enc.rs1_zero)

                m.d.comb += self.funct3_v.eq(enc.funct3 is not None)
                m.d.comb += self.funct7_v.eq(enc.funct7 is not None)
                m.d.comb += self.funct12_v.eq(enc.funct12 is not None)

        # Destination and source registers validity

        m.d.comb += [
            self.rd_v.eq(reduce(or_, (instruction_type == t for t in _rd_itypes)) & ~rd_invalid),
            self.rs1_v.eq(reduce(or_, (instruction_type == t for t in _rs1_itypes)) & ~rs1_invalid),
            self.rs2_v.eq(reduce(or_, (instruction_type == t for t in _rs2_itypes)) & ~self.funct12_v),
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

        with m.If((opcode == Opcode.OP_IMM) & ((self.funct3 == Funct3.SLL) | (self.funct3 == Funct3.SR))):
            m.d.comb += iimm12.eq(instr[20:25])

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

        # CSR with immediate correction

        with m.If(self.optype == OpType.CSR_IMM):
            m.d.comb += [
                self.imm.eq(uimm5),
                self.rs1_v.eq(0),
            ]

        # Instruction simplification

        # lui rd, imm -> addi rd, x0, (imm << 12)
        with m.If(opcode == Opcode.LUI):
            m.d.comb += [
                self.opcode.eq(Opcode.OP_IMM),
                self.funct3.eq(Funct3.ADD),
                self.funct3_v.eq(1),
                self.rs1.eq(0),
                self.rs1_v.eq(1),
            ]
        with m.Else():
            m.d.comb += self.opcode.eq(opcode)

        # Illegal instruction detection
        encoding_space = Signal(2)
        m.d.comb += self._extract(0, encoding_space)
        m.d.comb += self.illegal.eq((self.optype == OpType.UNKNOWN) | (encoding_space != 0b11))

        return m
