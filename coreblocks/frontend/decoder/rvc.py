from amaranth import *

from transactron import TModule
from transactron.utils import ValueLike

from coreblocks.params import *
from coreblocks.arch import *


# An instruction or an instruction with the valid signal
DecodedInstr = ValueLike | tuple[ValueLike, ValueLike]


def is_instr_compressed(instr: Value) -> Value:
    return instr[0:2] != 0b11


class InstrDecompress(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params

        #
        # Input ports
        #

        self.instr_in = Signal(16)

        #
        # Output ports
        #
        self.instr_out = Signal(32)

    def decompr_reg(self, rvc_reg: Value) -> Value:
        return Cat(rvc_reg, C(0b01, 2))

    def instr_mux(self, sel: Value, inputs: list[DecodedInstr]) -> tuple[ValueLike, ValueLike]:
        if 2 ** len(sel) != len(inputs):
            raise RuntimeError(
                f"Length of inputs ({len(inputs)}) is not equal to two to the power of length of sel ({len(sel)})"
            )

        instr = Array([instr[0] if isinstance(instr, tuple) else instr for instr in inputs])[sel]
        legal = Array([instr[1] if isinstance(instr, tuple) else 1 for instr in inputs])[sel]
        return (instr, legal)

    def _quadrant_0(self) -> list[DecodedInstr]:
        rs1 = self.decompr_reg(self.instr_in[7:10])
        rs2 = self.decompr_reg(self.instr_in[2:5])
        rd = self.decompr_reg(self.instr_in[2:5])

        addi4spn_imm = Cat(
            C(0, 2), self.instr_in[6], self.instr_in[5], self.instr_in[11:13], self.instr_in[7:11], C(0, 2)
        )
        lsd_imm = Cat(C(0, 3), self.instr_in[10:13], self.instr_in[5:7], C(0, 4))
        lsw_imm = Cat(C(0, 2), self.instr_in[6], self.instr_in[10:13], self.instr_in[5], C(0, 5))

        addi4spn = (
            ITypeInstr(opcode=Opcode.OP_IMM, rd=rd, funct3=Funct3.ADD, rs1=Registers.SP, imm=addi4spn_imm),
            addi4spn_imm.any(),
        )
        reserved = (IllegalInstr(), 0)

        if self.gen_params.isa.extensions & Extension.D:
            fld = ITypeInstr(opcode=Opcode.LOAD_FP, rd=rd, funct3=Funct3.D, rs1=rs1, imm=lsd_imm)
            fsd = STypeInstr(opcode=Opcode.STORE_FP, imm=lsd_imm, funct3=Funct3.D, rs1=rs1, rs2=rs2)
        else:
            fld = (IllegalInstr(), 0)
            fsd = (IllegalInstr(), 0)

        lw = ITypeInstr(opcode=Opcode.LOAD, rd=rd, funct3=Funct3.W, rs1=rs1, imm=lsw_imm)
        sw = STypeInstr(opcode=Opcode.STORE, imm=lsw_imm, funct3=Funct3.W, rs1=rs1, rs2=rs2)

        if self.gen_params.isa.extensions & Extension.F and self.gen_params.isa.xlen == 32:
            flw = ITypeInstr(opcode=Opcode.LOAD_FP, rd=rd, funct3=Funct3.W, rs1=rs1, imm=lsw_imm)
            fsw = STypeInstr(opcode=Opcode.STORE_FP, imm=lsw_imm, funct3=Funct3.W, rs1=rs1, rs2=rs2)
        else:
            flw = (IllegalInstr(), 0)
            fsw = (IllegalInstr(), 0)

        if self.gen_params.isa.xlen == 64:
            ld = ITypeInstr(opcode=Opcode.LOAD, rd=rd, funct3=Funct3.D, rs1=rs1, imm=lsd_imm)
            sd = STypeInstr(opcode=Opcode.STORE, imm=lsd_imm, funct3=Funct3.D, rs1=rs1, rs2=rs2)
        else:
            ld = (IllegalInstr(), 0)
            sd = (IllegalInstr(), 0)

        return [
            addi4spn,
            fld,
            lw,
            flw if self.gen_params.isa.xlen == 32 else ld,
            reserved,
            fsd,
            sw,
            fsw if self.gen_params.isa.xlen == 32 else sd,
        ]

    def _quadrant_1(self) -> list[DecodedInstr]:
        rd_rs1 = self.decompr_reg(self.instr_in[7:10])
        rs2 = self.decompr_reg(self.instr_in[2:5])
        rd = self.instr_in[7:12]

        addi_imm = Cat(self.instr_in[2:7], self.instr_in[12].replicate(7))
        addi16sp_imm = Cat(
            C(0, 4),
            self.instr_in[6],
            self.instr_in[2],
            self.instr_in[5],
            self.instr_in[3:5],
            self.instr_in[12].replicate(3),
        )
        lui_imm = Cat(C(0, 12), self.instr_in[2:7], self.instr_in[12].replicate(15))
        j_imm = Cat(
            C(0, 1),
            self.instr_in[3:6],
            self.instr_in[11],
            self.instr_in[2],
            self.instr_in[7],
            self.instr_in[6],
            self.instr_in[9:11],
            self.instr_in[8],
            self.instr_in[12].replicate(10),
        )
        b_imm = Cat(
            C(0, 1),
            self.instr_in[3:5],
            self.instr_in[10:12],
            self.instr_in[2],
            self.instr_in[5:7],
            self.instr_in[12].replicate(5),
        )
        shamt = Cat(self.instr_in[2:7], self.instr_in[12])

        addi = ITypeInstr(opcode=Opcode.OP_IMM, rd=rd, funct3=Funct3.ADD, rs1=rd, imm=addi_imm)
        addiw = (ITypeInstr(opcode=Opcode.OP_IMM_32, rd=rd, funct3=Funct3.ADD, rs1=rd, imm=addi_imm), rd.any())
        addi16sp = (
            ITypeInstr(opcode=Opcode.OP_IMM, rd=Registers.SP, funct3=Funct3.ADD, rs1=Registers.SP, imm=addi16sp_imm),
            addi16sp_imm.any(),
        )

        li = ITypeInstr(opcode=Opcode.OP_IMM, rd=rd, funct3=Funct3.ADD, rs1=Registers.ZERO, imm=addi_imm)
        liu = (UTypeInstr(opcode=Opcode.LUI, rd=rd, imm=lui_imm), lui_imm.any())

        jal = JTypeInstr(opcode=Opcode.JAL, rd=Registers.RA, imm=j_imm)
        j = JTypeInstr(opcode=Opcode.JAL, rd=Registers.ZERO, imm=j_imm)

        beqz = BTypeInstr(opcode=Opcode.BRANCH, imm=b_imm, funct3=Funct3.BEQ, rs1=rd_rs1, rs2=Registers.ZERO)
        bnez = BTypeInstr(opcode=Opcode.BRANCH, imm=b_imm, funct3=Funct3.BNE, rs1=rd_rs1, rs2=Registers.ZERO)

        srli = (
            RTypeInstr(
                opcode=Opcode.OP_IMM,
                rd=rd_rs1,
                funct3=Funct3.SR,
                rs1=rd_rs1,
                rs2=shamt[0:5],
                funct7=Funct7.SL | shamt[5],
            ),
            ~shamt[5] if self.gen_params.isa.xlen == 32 else 1,
        )
        srai = (
            RTypeInstr(
                opcode=Opcode.OP_IMM,
                rd=rd_rs1,
                funct3=Funct3.SR,
                rs1=rd_rs1,
                rs2=shamt[0:5],
                funct7=Funct7.SA | shamt[5],
            ),
            ~shamt[5] if self.gen_params.isa.xlen == 32 else 1,
        )
        andi = ITypeInstr(opcode=Opcode.OP_IMM, rd=rd_rs1, funct3=Funct3.AND, rs1=rd_rs1, imm=addi_imm)

        sub = RTypeInstr(opcode=Opcode.OP, rd=rd_rs1, funct3=Funct3.SUB, rs1=rd_rs1, rs2=rs2, funct7=Funct7.SUB)
        xor = RTypeInstr(opcode=Opcode.OP, rd=rd_rs1, funct3=Funct3.XOR, rs1=rd_rs1, rs2=rs2, funct7=Funct7.XOR)
        or_ = RTypeInstr(opcode=Opcode.OP, rd=rd_rs1, funct3=Funct3.OR, rs1=rd_rs1, rs2=rs2, funct7=Funct7.OR)
        and_ = RTypeInstr(opcode=Opcode.OP, rd=rd_rs1, funct3=Funct3.AND, rs1=rd_rs1, rs2=rs2, funct7=Funct7.AND)
        rtype = self.instr_mux(self.instr_in[5:7], [sub, xor, or_, and_])

        if self.gen_params.isa.xlen != 32:
            subw = (
                RTypeInstr(opcode=Opcode.OP32, rd=rd_rs1, funct3=Funct3.SUB, rs1=rd_rs1, rs2=rs2, funct7=Funct3.SUB),
                ~self.instr_in[6],
            )
            addw = (
                RTypeInstr(opcode=Opcode.OP32, rd=rd_rs1, funct3=Funct3.ADD, rs1=rd_rs1, rs2=rs2, funct7=Funct3.ADD),
                ~self.instr_in[6],
            )
            w = self.instr_mux(self.instr_in[5], [subw, addw])

            rtype = self.instr_mux(self.instr_in[12], [rtype, w])
        else:
            rtype = (rtype[0], rtype[1] & ~self.instr_in[12])

        return [
            addi,
            jal if self.gen_params.isa.xlen == 32 else addiw,
            li,
            self.instr_mux(rd == Registers.SP, [liu, addi16sp]),
            self.instr_mux(self.instr_in[10:12], [srli, srai, andi, rtype]),
            j,
            beqz,
            bnez,
        ]

    def _quadrant_2(self) -> list[DecodedInstr]:
        rd_rs1 = self.instr_in[7:12]
        rs2 = self.instr_in[2:7]

        shamt = Cat(self.instr_in[2:7], self.instr_in[12])
        ldsp_imm = Cat(C(0, 3), self.instr_in[5:7], self.instr_in[12], self.instr_in[2:5], C(0, 3))
        lwsp_imm = Cat(C(0, 2), self.instr_in[4:7], self.instr_in[12], self.instr_in[2:4], C(0, 4))
        sdsp_imm = Cat(C(0, 3), self.instr_in[10:13], self.instr_in[7:10], C(0, 3))
        swsp_imm = Cat(C(0, 2), self.instr_in[9:13], self.instr_in[7:9], C(0, 4))

        slli = (
            RTypeInstr(
                opcode=Opcode.OP_IMM,
                rd=rd_rs1,
                funct3=Funct3.SLL,
                rs1=rd_rs1,
                rs2=shamt[0:5],
                funct7=Funct7.SL | shamt[5],
            ),
            ~shamt[5] if self.gen_params.isa.xlen == 32 else 1,
        )

        if (
            self.gen_params.isa.xlen == 32 or self.gen_params.isa.xlen == 64
        ) and self.gen_params.isa.extensions & Extension.D:
            fldsp = ITypeInstr(opcode=Opcode.LOAD_FP, rd=rd_rs1, funct3=Funct3.D, rs1=Registers.SP, imm=ldsp_imm)
            fsdsp = STypeInstr(opcode=Opcode.STORE_FP, imm=sdsp_imm, funct3=Funct3.D, rs1=Registers.SP, rs2=rs2)
        else:
            fldsp = (IllegalInstr(), 0)
            fsdsp = (IllegalInstr(), 0)

        lwsp = (
            ITypeInstr(opcode=Opcode.LOAD, rd=rd_rs1, funct3=Funct3.W, rs1=Registers.SP, imm=lwsp_imm),
            rd_rs1.any(),
        )
        swsp = STypeInstr(opcode=Opcode.STORE, imm=swsp_imm, funct3=Funct3.W, rs1=Registers.SP, rs2=rs2)

        if self.gen_params.isa.extensions & Extension.F:
            flwsp = ITypeInstr(opcode=Opcode.LOAD_FP, rd=rd_rs1, funct3=Funct3.W, rs1=Registers.SP, imm=lwsp_imm)
            fswsp = STypeInstr(opcode=Opcode.STORE_FP, imm=swsp_imm, funct3=Funct3.W, rs1=Registers.SP, rs2=rs2)
        else:
            flwsp = (IllegalInstr(), 0)
            fswsp = (IllegalInstr(), 0)

        ldsp = ITypeInstr(opcode=Opcode.LOAD, rd=rd_rs1, funct3=Funct3.D, rs1=Registers.SP, imm=ldsp_imm)
        sdsp = STypeInstr(opcode=Opcode.STORE, imm=sdsp_imm, funct3=Funct3.D, rs1=Registers.SP, rs2=rs2)

        jr = (
            ITypeInstr(opcode=Opcode.JALR, rd=Registers.ZERO, funct3=Funct3.JALR, rs1=rd_rs1, imm=C(0, 12)),
            rd_rs1.any(),
        )
        jalr = ITypeInstr(opcode=Opcode.JALR, rd=Registers.RA, funct3=Funct3.JALR, rs1=rd_rs1, imm=C(0, 12))

        ebreak = EBreakInstr()

        mv = RTypeInstr(opcode=Opcode.OP, rd=rd_rs1, funct3=Funct3.ADD, rs1=Registers.ZERO, rs2=rs2, funct7=Funct7.ADD)
        add = RTypeInstr(opcode=Opcode.OP, rd=rd_rs1, funct3=Funct3.ADD, rs1=rd_rs1, rs2=rs2, funct7=Funct7.ADD)

        jr_mv = self.instr_mux(rs2.any(), [jr, mv])
        ebreak_jalr = self.instr_mux(rd_rs1.any(), [ebreak, jalr])
        ebreak_jalr_add = self.instr_mux(rs2.any(), [ebreak_jalr, add])

        return [
            slli,
            fldsp,
            lwsp,
            flwsp if self.gen_params.isa.xlen == 32 else ldsp,
            self.instr_mux(self.instr_in[12], [jr_mv, ebreak_jalr_add]),
            fsdsp,
            swsp,
            fswsp if self.gen_params.isa.xlen == 32 else sdsp,
        ]

    def elaborate(self, platform):
        m = TModule()

        funct3 = self.instr_in[13:16]
        quadrant = self.instr_in[0:2]

        quadrants: list[DecodedInstr] = [
            self.instr_mux(funct3, q) for q in [self._quadrant_0(), self._quadrant_1(), self._quadrant_2()]
        ]

        # Quadrant 3 is reserved for longer (>16bit) instructions
        quadrants.append((IllegalInstr(), 0))

        res = self.instr_mux(quadrant, quadrants)

        m.d.comb += self.instr_out.eq(Mux(res[1], res[0], IllegalInstr()))

        return m
