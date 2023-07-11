from coreblocks.params import Funct3, Funct7, OpType
from coreblocks.fu.alu import AluFn, ALUComponent

from test.fu.functional_common import FunctionalUnitTestCase

from test.common import signed_to_int


class AluUnitTest(FunctionalUnitTestCase[AluFn.Fn]):
    func_unit = ALUComponent(zba_enable=True, zbb_enable=True)
    zero_imm = False

    ops = {
        AluFn.Fn.ADD: {
            "op_type": OpType.ARITHMETIC,
            "funct3": Funct3.ADD,
            "funct7": Funct7.ADD,
        },
        AluFn.Fn.SUB: {
            "op_type": OpType.ARITHMETIC,
            "funct3": Funct3.ADD,
            "funct7": Funct7.SUB,
        },
        AluFn.Fn.SLT: {
            "op_type": OpType.COMPARE,
            "funct3": Funct3.SLT,
        },
        AluFn.Fn.SLTU: {
            "op_type": OpType.COMPARE,
            "funct3": Funct3.SLTU,
        },
        AluFn.Fn.XOR: {
            "op_type": OpType.LOGIC,
            "funct3": Funct3.XOR,
        },
        AluFn.Fn.OR: {
            "op_type": OpType.LOGIC,
            "funct3": Funct3.OR,
        },
        AluFn.Fn.AND: {
            "op_type": OpType.LOGIC,
            "funct3": Funct3.AND,
        },
        AluFn.Fn.SH1ADD: {
            "op_type": OpType.ADDRESS_GENERATION,
            "funct3": Funct3.SH1ADD,
            "funct7": Funct7.SH1ADD,
        },
        AluFn.Fn.SH2ADD: {
            "op_type": OpType.ADDRESS_GENERATION,
            "funct3": Funct3.SH2ADD,
            "funct7": Funct7.SH2ADD,
        },
        AluFn.Fn.SH3ADD: {
            "op_type": OpType.ADDRESS_GENERATION,
            "funct3": Funct3.SH3ADD,
            "funct7": Funct7.SH3ADD,
        },
        AluFn.Fn.ANDN: {
            "op_type": OpType.BIT_MANIPULATION,
            "funct3": Funct3.ANDN,
            "funct7": Funct7.ANDN,
        },
        AluFn.Fn.XNOR: {
            "op_type": OpType.BIT_MANIPULATION,
            "funct3": Funct3.XNOR,
            "funct7": Funct7.XNOR,
        },
        AluFn.Fn.ORN: {
            "op_type": OpType.BIT_MANIPULATION,
            "funct3": Funct3.ORN,
            "funct7": Funct7.ORN,
        },
        AluFn.Fn.MAX: {
            "op_type": OpType.BIT_MANIPULATION,
            "funct3": Funct3.MAX,
            "funct7": Funct7.MAX,
        },
        AluFn.Fn.MAXU: {
            "op_type": OpType.BIT_MANIPULATION,
            "funct3": Funct3.MAXU,
            "funct7": Funct7.MAX,
        },
        AluFn.Fn.MIN: {
            "op_type": OpType.BIT_MANIPULATION,
            "funct3": Funct3.MIN,
            "funct7": Funct7.MIN,
        },
        AluFn.Fn.MINU: {
            "op_type": OpType.BIT_MANIPULATION,
            "funct3": Funct3.MINU,
            "funct7": Funct7.MIN,
        },
        AluFn.Fn.CPOP: {
            "op_type": OpType.UNARY_BIT_MANIPULATION_5,
            "funct3": Funct3.CPOP,
            "funct7": Funct7.CPOP,
        },
        AluFn.Fn.SEXTB: {
            "op_type": OpType.UNARY_BIT_MANIPULATION_1,
            "funct3": Funct3.SEXTB,
            "funct7": Funct7.SEXTB,
        },
        AluFn.Fn.ZEXTH: {
            "op_type": OpType.UNARY_BIT_MANIPULATION_1,
            "funct3": Funct3.ZEXTH,
            "funct7": Funct7.ZEXTH,
        },
        AluFn.Fn.SEXTH: {
            "op_type": OpType.UNARY_BIT_MANIPULATION_2,
            "funct3": Funct3.SEXTH,
            "funct7": Funct7.SEXTH,
        },
        AluFn.Fn.ORCB: {
            "op_type": OpType.UNARY_BIT_MANIPULATION_1,
            "funct3": Funct3.ORCB,
            "funct7": Funct7.ORCB,
        },
        AluFn.Fn.REV8: {
            "op_type": OpType.UNARY_BIT_MANIPULATION_1,
            "funct3": Funct3.REV8,
            "funct7": Funct7.REV8,
        },
        AluFn.Fn.CLZ: {
            "op_type": OpType.UNARY_BIT_MANIPULATION_3,
            "funct3": Funct3.CLZ,
            "funct7": Funct7.CLZ,
        },
        AluFn.Fn.CTZ: {
            "op_type": OpType.UNARY_BIT_MANIPULATION_4,
            "funct3": Funct3.CTZ,
            "funct7": Funct7.CTZ,
        },
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
