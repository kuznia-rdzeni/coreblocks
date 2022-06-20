from functools import reduce
from itertools import starmap
from operator import or_
from typing import Union

from amaranth import *

from coreblocks.genparams import GenParams
from coreblocks.isa import *

__all__ = ["InstrDecoder"]

_rd_itypes = [InstrType.R, InstrType.I, InstrType.U, InstrType.J]

_rs1_itypes = [InstrType.R, InstrType.I, InstrType.S, InstrType.B]

_rs2_itypes = [InstrType.R, InstrType.S, InstrType.B]


class Encoding:
    def __init__(
        self,
        opcode: Opcode,
        funct3: Union[Funct3, None] = None,
        funct7: Union[Funct7, None] = None,
        funct12: Union[Funct12, None] = None,
    ):
        self.opcode = opcode
        self.funct3 = funct3
        self.funct7 = funct7
        self.funct12 = funct12


#
# Instructions groupped by `OpType`
#

_arithmetic_encodings = [
    Encoding(Opcode.OP_IMM, Funct3.ADD),  # addi
    Encoding(Opcode.OP, Funct3.ADD, Funct7.ADD),  # add
    Encoding(Opcode.OP, Funct3.ADD, Funct7.SUB),  # sub
    Encoding(Opcode.LUI),  # lui
]

_compare_encodings = [
    Encoding(Opcode.OP_IMM, Funct3.SLT),  # slti
    Encoding(Opcode.OP_IMM, Funct3.SLTU),  # sltiu
    Encoding(Opcode.OP, Funct3.SLT, Funct7.SLT),  # slt
    Encoding(Opcode.OP, Funct3.SLTU, Funct7.SLT),  # sltu
]

_logic_encodings = [
    Encoding(Opcode.OP_IMM, Funct3.XOR),  # xori
    Encoding(Opcode.OP_IMM, Funct3.OR),  # ori
    Encoding(Opcode.OP_IMM, Funct3.AND),  # andi
    Encoding(Opcode.OP, Funct3.XOR, Funct7.XOR),  # xor
    Encoding(Opcode.OP, Funct3.OR, Funct7.OR),  # or
    Encoding(Opcode.OP, Funct3.AND, Funct7.AND),  # and
]

_shift_encodings = [
    Encoding(Opcode.OP_IMM, Funct3.SLL, Funct7.SL),  # slli
    Encoding(Opcode.OP_IMM, Funct3.SR, Funct7.SL),  # srli
    Encoding(Opcode.OP_IMM, Funct3.SR, Funct7.SA),  # srai
    Encoding(Opcode.OP, Funct3.SLL, Funct7.SL),  # sll
    Encoding(Opcode.OP, Funct3.SR, Funct7.SL),  # srl
    Encoding(Opcode.OP, Funct3.SR, Funct7.SA),  # sra
]

_auipc_encodings = [
    Encoding(Opcode.AUIPC),  # auipc
]

_jump_encodings = [
    Encoding(Opcode.JAL),  # jal
    Encoding(Opcode.JALR, Funct3.JALR),  # jalr
]

_branch_encodings = [
    Encoding(Opcode.BRANCH, Funct3.BEQ),  # beq
    Encoding(Opcode.BRANCH, Funct3.BNE),  # bne
    Encoding(Opcode.BRANCH, Funct3.BLT),  # blt
    Encoding(Opcode.BRANCH, Funct3.BGE),  # bge
    Encoding(Opcode.BRANCH, Funct3.BLTU),  # bltu
    Encoding(Opcode.BRANCH, Funct3.BGEU),  # bgeu
]

_load_encodings = [
    Encoding(Opcode.LOAD, Funct3.B),  # lb
    Encoding(Opcode.LOAD, Funct3.BU),  # lbu
    Encoding(Opcode.LOAD, Funct3.H),  # lh
    Encoding(Opcode.LOAD, Funct3.HU),  # lhu
    Encoding(Opcode.LOAD, Funct3.W),  # lw
]

_store_encodings = [
    Encoding(Opcode.STORE, Funct3.B),  # sb
    Encoding(Opcode.STORE, Funct3.H),  # sh
    Encoding(Opcode.STORE, Funct3.W),  # sw
]

_fence_encodings = [
    Encoding(Opcode.MISC_MEM, Funct3.FENCE),  # fence
]

_ecall_encodings = [
    Encoding(Opcode.SYSTEM, Funct3.PRIV, None, Funct12.ECALL),  # ecall
]

_ebreak_encodings = [
    Encoding(Opcode.SYSTEM, Funct3.PRIV, None, Funct12.EBREAK),  # ebreak
]

_mret_encodings = [
    Encoding(Opcode.SYSTEM, Funct3.PRIV, None, Funct12.MRET),  # mret
]

_wfi_encodings = [
    Encoding(Opcode.SYSTEM, Funct3.PRIV, None, Funct12.WFI),  # wfi
]

_fencei_encodings = [
    Encoding(Opcode.MISC_MEM, Funct3.FENCEI),  # fence.i
]

_csr_encodings = [
    Encoding(Opcode.SYSTEM, Funct3.CSRRW),  # csrrw
    Encoding(Opcode.SYSTEM, Funct3.CSRRS),  # csrrs
    Encoding(Opcode.SYSTEM, Funct3.CSRRC),  # csrrc
    Encoding(Opcode.SYSTEM, Funct3.CSRRWI),  # csrrwi
    Encoding(Opcode.SYSTEM, Funct3.CSRRSI),  # csrrsi
    Encoding(Opcode.SYSTEM, Funct3.CSRRCI),  # csrrci
]

#
# Encodings groupped by extensions
#

_i_encodings = [
    _arithmetic_encodings,
    _compare_encodings,
    _logic_encodings,
    _shift_encodings,
    _auipc_encodings,
    _jump_encodings,
    _branch_encodings,
    _load_encodings,
    _store_encodings,
    _fence_encodings,
    _ecall_encodings,
    _ebreak_encodings,
    _mret_encodings,
    _wfi_encodings,
]

_zifencei_encodings = [
    _fencei_encodings,
]

_zicsr_encodings = [
    _csr_encodings,
]


class InstrDecoder(Elaboratable):
    def __init__(self, gen: GenParams):
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
        self.funct7 = Signal(Funct7)
        self.funct12 = Signal(Funct12)

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

    def _extract(self, start, sig):
        return sig.eq(self.instr[start : start + len(sig)])

    def _match(self, encodings):
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

        # Opcode and funct

        opcode = Signal(Opcode)

        m.d.comb += [
            self._extract(2, opcode),
            self._extract(12, self.funct3),
            self._extract(25, self.funct7),
            self._extract(20, self.funct12),
        ]

        # Instruction type

        itype = Signal(InstrType)
        opcode_iv = Signal()

        with m.Switch(opcode):
            with m.Case(Opcode.OP_IMM, Opcode.JALR, Opcode.LOAD, Opcode.MISC_MEM, Opcode.SYSTEM):
                m.d.comb += itype.eq(InstrType.I)
            with m.Case(Opcode.LUI, Opcode.AUIPC):
                m.d.comb += itype.eq(InstrType.U)
            with m.Case(Opcode.OP):
                m.d.comb += itype.eq(InstrType.R)
            with m.Case(Opcode.JAL):
                m.d.comb += itype.eq(InstrType.J)
            with m.Case(Opcode.BRANCH):
                m.d.comb += itype.eq(InstrType.B)
            with m.Case(Opcode.STORE):
                m.d.comb += itype.eq(InstrType.S)
            with m.Default():
                m.d.comb += opcode_iv.eq(1)

        # Destination and source registers

        m.d.comb += [
            self._extract(7, self.rd),
            self.rd_v.eq(reduce(or_, (itype == t for t in _rd_itypes))),
            self._extract(15, self.rs1),
            self.rs1_v.eq(reduce(or_, (itype == t for t in _rs1_itypes))),
            self._extract(20, self.rs2),
            self.rs2_v.eq(reduce(or_, (itype == t for t in _rs2_itypes))),
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

        with m.Switch(itype):
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

        op_mask = Signal(len(list(OpType)) - 1)
        extensions = self.gen.isa.extensions

        m.d.comb += op_mask.eq(0)
        for i, encodings in enumerate(_i_encodings):
            m.d.comb += op_mask[i].eq(self._match(encodings))

        off = len(_i_encodings)

        if extensions & Extension.ZIFENCEI:
            for i, encodings in enumerate(_zifencei_encodings):
                m.d.comb += op_mask[i + off].eq(self._match(encodings))

        off += len(_zifencei_encodings)

        if extensions & Extension.ZICSR:
            for i, encodings in enumerate(_zicsr_encodings):
                m.d.comb += op_mask[i + off].eq(self._match(encodings))

        off += len(_zicsr_encodings)

        m.d.comb += self.op.eq(OpType.UNKNOWN)
        with m.Switch(op_mask):
            for i in range(off):
                with m.Case("-" * (len(op_mask) - i - 1) + "1" + "-" * i):
                    m.d.comb += self.op.eq(i + 1)
            with m.Default():
                m.d.comb += self.op.eq(OpType.UNKNOWN)

        # Instruction simplification

        # lui rd, imm -> addi rd, x0, (imm << 12)
        with m.If(opcode == Opcode.LUI):
            m.d.comb += [
                self.opcode.eq(Opcode.OP_IMM),
                self.funct3.eq(Funct3.ADD),
                self.rs1.eq(0),
            ]
        with m.Else():
            m.d.comb += self.opcode.eq(opcode)

        # Immediate correction

        with m.If(self.op == OpType.CSR):
            m.d.comb += self.imm.eq(uimm5)

        # Illegal instruction detection

        m.d.comb += self.illegal.eq(opcode_iv | (self.op == OpType.UNKNOWN))

        return m
