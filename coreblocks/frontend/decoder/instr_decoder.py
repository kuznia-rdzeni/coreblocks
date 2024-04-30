from functools import reduce
from operator import or_

from amaranth import *

from coreblocks.params import *
from coreblocks.arch import *
from coreblocks.arch.optypes import optypes_by_extensions
from .instr_description import instructions_by_optype, Encoding

__all__ = ["InstrDecoder"]

# Important
#
# In order to add new instructions to be decoded by this decoder assuming they do not required additional
# fields to be extracted you need to add them into `instructions_by_optype` map, and register new OpType
# into new or existing extension in `optypes_by_extensions` map in `params.optypes` module.

# Lists which fields are used by which Instruction's types

_rd_itypes = [InstrType.R, InstrType.I, InstrType.U, InstrType.J]

_rs1_itypes = [InstrType.R, InstrType.I, InstrType.S, InstrType.B]

_rs2_itypes = [InstrType.R, InstrType.S, InstrType.B]


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

    def __init__(self, gen_params: GenParams):
        """
        Decoder constructor.

        Parameters
        ----------
        gen_params: GenParams
            Core generation parameters.
        """
        self.gen_params = gen_params

        #
        # Input ports
        #

        self.instr = Signal(gen_params.isa.ilen)

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
        self.rd = Signal(gen_params.isa.reg_cnt_log)
        self.rd_v = Signal()

        # First source register
        self.rs1 = Signal(gen_params.isa.reg_cnt_log)
        self.rs1_v = Signal()

        # Second source register
        self.rs2 = Signal(gen_params.isa.reg_cnt_log)
        self.rs2_v = Signal()

        # Immediate
        self.imm = Signal(gen_params.isa.xlen)

        # Fence parameters
        self.succ = Signal(FenceTarget)
        self.pred = Signal(FenceTarget)
        self.fm = Signal(FenceFm)

        # CSR address
        self.csr = Signal(gen_params.isa.csr_alen)

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

        extensions = self.gen_params.isa.extensions

        # We need to support all I instructions in E extension, but this is not extension implication
        if Extension.E in extensions:
            extensions |= Extension.I

        supported_encodings: set[Encoding] = set()
        encoding_to_optype: dict[Encoding, OpType] = dict()
        for ext, optypes in optypes_by_extensions.items():
            if extensions & ext:
                for optype in optypes:
                    for encoding in instructions_by_optype[optype]:
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

        rd_field = Signal(self.gen_params.isa.reg_field_bits)
        rs1_field = Signal(self.gen_params.isa.reg_field_bits)
        rs2_field = Signal(self.gen_params.isa.reg_field_bits)

        m.d.comb += [
            self._extract(7, rd_field),
            self._extract(15, rs1_field),
            self._extract(20, rs2_field),
        ]

        m.d.comb += [
            self.rd.eq(rd_field),
            self.rs1.eq(rs1_field),
            self.rs2.eq(rs2_field),
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
                m.d.comb += self.imm.eq(uimm20 << (self.gen_params.isa.xlen - 20))
            with m.Case(InstrType.J):
                m.d.comb += self.imm.eq(jimm20)

        # Fence parameters

        m.d.comb += [
            self._extract(20, self.succ),
            self._extract(24, self.pred),
            self._extract(28, self.fm),
        ]

        # Check if register field bits outside of logical register space are zeroed

        register_space_invalid = Signal()
        m.d.comb += register_space_invalid.eq(
            (self.rd_v & (rd_field[len(self.rd) :]).any())
            | (self.rs1_v & (rs1_field[len(self.rs1) :]).any())
            | (self.rs2_v & (rs2_field[len(self.rs2) :]).any())
        )

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
        # 0b11 at field [0:2] of instruction specify standard 32-bit instruction encoding space (not checked by opcode)
        encoding_space = Signal(2)
        m.d.comb += self._extract(0, encoding_space)
        m.d.comb += self.illegal.eq((self.optype == OpType.UNKNOWN) | (encoding_space != 0b11) | register_space_invalid)

        return m
