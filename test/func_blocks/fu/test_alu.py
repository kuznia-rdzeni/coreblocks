from coreblocks.arch import Funct3, Funct7, OpType
from coreblocks.func_blocks.fu.alu import AluFn, ALUComponent

from test.func_blocks.fu.functional_common import ExecFn, FunctionalUnitTestCase

from transactron.utils import signed_to_int


class TestAluUnit(FunctionalUnitTestCase[AluFn.Fn]):
    func_unit = ALUComponent(zba_enable=True, zbb_enable=True)
    zero_imm = False

    ops = {
        AluFn.Fn.ADD: ExecFn(OpType.ARITHMETIC, Funct3.ADD, Funct7.ADD),
        AluFn.Fn.SUB: ExecFn(OpType.ARITHMETIC, Funct3.ADD, Funct7.SUB),
        AluFn.Fn.SLT: ExecFn(OpType.COMPARE, Funct3.SLT),
        AluFn.Fn.SLTU: ExecFn(OpType.COMPARE, Funct3.SLTU),
        AluFn.Fn.XOR: ExecFn(OpType.LOGIC, Funct3.XOR),
        AluFn.Fn.OR: ExecFn(OpType.LOGIC, Funct3.OR),
        AluFn.Fn.AND: ExecFn(OpType.LOGIC, Funct3.AND),
        AluFn.Fn.SH1ADD: ExecFn(OpType.ADDRESS_GENERATION, Funct3.SH1ADD, Funct7.SH1ADD),
        AluFn.Fn.SH2ADD: ExecFn(OpType.ADDRESS_GENERATION, Funct3.SH2ADD, Funct7.SH2ADD),
        AluFn.Fn.SH3ADD: ExecFn(OpType.ADDRESS_GENERATION, Funct3.SH3ADD, Funct7.SH3ADD),
        AluFn.Fn.ANDN: ExecFn(OpType.BIT_MANIPULATION, Funct3.ANDN, Funct7.ANDN),
        AluFn.Fn.XNOR: ExecFn(OpType.BIT_MANIPULATION, Funct3.XNOR, Funct7.XNOR),
        AluFn.Fn.ORN: ExecFn(OpType.BIT_MANIPULATION, Funct3.ORN, Funct7.ORN),
        AluFn.Fn.MAX: ExecFn(OpType.BIT_MANIPULATION, Funct3.MAX, Funct7.MAX),
        AluFn.Fn.MAXU: ExecFn(OpType.BIT_MANIPULATION, Funct3.MAXU, Funct7.MAX),
        AluFn.Fn.MIN: ExecFn(OpType.BIT_MANIPULATION, Funct3.MIN, Funct7.MIN),
        AluFn.Fn.MINU: ExecFn(OpType.BIT_MANIPULATION, Funct3.MINU, Funct7.MIN),
        AluFn.Fn.SEXTB: ExecFn(OpType.UNARY_BIT_MANIPULATION_1, Funct3.SEXTB),
        AluFn.Fn.ZEXTH: ExecFn(OpType.UNARY_BIT_MANIPULATION_1, Funct3.ZEXTH),
        AluFn.Fn.REV8: ExecFn(OpType.UNARY_BIT_MANIPULATION_1, Funct3.REV8),
        AluFn.Fn.SEXTH: ExecFn(OpType.UNARY_BIT_MANIPULATION_2, Funct3.SEXTH),
        AluFn.Fn.ORCB: ExecFn(OpType.UNARY_BIT_MANIPULATION_2, Funct3.ORCB),
        AluFn.Fn.CLZ: ExecFn(OpType.UNARY_BIT_MANIPULATION_3, Funct3.CLZ),
        AluFn.Fn.CTZ: ExecFn(OpType.UNARY_BIT_MANIPULATION_4, Funct3.CTZ),
        AluFn.Fn.CPOP: ExecFn(OpType.UNARY_BIT_MANIPULATION_5, Funct3.CPOP),
    }

    @staticmethod
    def compute_result(i1: int, i2: int, i_imm: int, pc: int, fn: AluFn.Fn, xlen: int) -> dict[str, int]:
        val2 = i_imm if i_imm else i2
        mask = (1 << xlen) - 1

        res = 0

        match fn:
            case AluFn.Fn.ADD:
                res = i1 + val2
            case AluFn.Fn.SUB:
                res = i1 - val2
            case AluFn.Fn.XOR:
                res = i1 ^ val2
            case AluFn.Fn.OR:
                res = i1 | val2
            case AluFn.Fn.AND:
                res = i1 & val2
            case AluFn.Fn.SLT:
                res = signed_to_int(i1, xlen) < signed_to_int(val2, xlen)
            case AluFn.Fn.SLTU:
                res = i1 < val2
            case AluFn.Fn.SH1ADD:
                res = (i1 << 1) + val2
            case AluFn.Fn.SH2ADD:
                res = (i1 << 2) + val2
            case AluFn.Fn.SH3ADD:
                res = (i1 << 3) + val2
            case AluFn.Fn.ANDN:
                res = i1 & ~val2
            case AluFn.Fn.XNOR:
                res = ~(i1 ^ val2)
            case AluFn.Fn.ORN:
                res = i1 | ~val2
            case AluFn.Fn.MAX:
                res = max(signed_to_int(i1, xlen), signed_to_int(val2, xlen))
            case AluFn.Fn.MAXU:
                res = max(i1, val2)
            case AluFn.Fn.MIN:
                res = min(signed_to_int(i1, xlen), signed_to_int(val2, xlen))
            case AluFn.Fn.MINU:
                res = min(i1, val2)
            case AluFn.Fn.CPOP:
                res = i1.bit_count()
            case AluFn.Fn.SEXTH:
                bit = (i1 >> 15) & 1
                if bit:
                    res = i1 | (mask ^ 0xFFFF)
                else:
                    res = i1 & 0xFFFF
            case AluFn.Fn.SEXTB:
                bit = (i1 >> 7) & 1
                if bit:
                    res = i1 | (mask ^ 0xFF)
                else:
                    res = i1 & 0xFF
            case AluFn.Fn.ZEXTH:
                res = i1 & 0xFFFF
            case AluFn.Fn.ORCB:
                i1 |= i1 >> 1
                i1 |= i1 >> 2
                i1 |= i1 >> 4

                i1 &= 0x010101010101010101

                for i in range(8):
                    res |= i1 << i
            case AluFn.Fn.REV8:
                for i in range(xlen // 8):
                    res = (res << 8) | (i1 & 0xFF)
                    i1 >>= 8  # Haskell screams in pain
            case AluFn.Fn.CLZ:
                res = xlen - i1.bit_length()
            case AluFn.Fn.CTZ:
                if i1 == 0:
                    res = xlen.bit_length()
                else:
                    while (i1 & 1) == 0:
                        res += 1
                        i1 >>= 1

        return {"result": res & mask}

    def test_fu(self):
        self.run_standard_fu_test()

    def test_pipeline(self):
        self.run_standard_fu_test(pipeline_test=True)
