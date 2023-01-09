import unittest

from coreblocks.params.isa import Extension, ISA


class TestISA(unittest.TestCase):
    class ISATestEntry:
        def __init__(self, isa_str, valid, xlen=None, reg_cnt=None, extensions=None):
            self.isa_str = isa_str
            self.valid = valid
            self.xlen = xlen
            self.reg_cnt = reg_cnt
            self.extensions = extensions

    ISA_TESTS = [
        ISATestEntry("rv32i", True, 32, 32, Extension.I),
        ISATestEntry("RV32I", True, 32, 32, Extension.I),
        ISATestEntry("rv32ima", True, 32, 32, Extension.I | Extension.M | Extension.A),
        ISATestEntry(
            "rv32imafdc_zicsr",
            True,
            32,
            32,
            Extension.I | Extension.M | Extension.A | Extension.F | Extension.D | Extension.C | Extension.ZICSR,
        ),
        ISATestEntry(
            "rv32izicsr",
            True,
            32,
            32,
            Extension.I | Extension.ZICSR,
        ),
        ISATestEntry(
            "rv32imczicsr",
            True,
            32,
            32,
            Extension.I | Extension.M | Extension.C | Extension.ZICSR,
        ),
        ISATestEntry(
            "rv32i_zmmul",
            True,
            32,
            32,
            Extension.I | Extension.ZMMUL,
        ),
        ISATestEntry(
            "rv32imafdc_zifencei_zicsr",
            True,
            32,
            32,
            Extension.I
            | Extension.M
            | Extension.A
            | Extension.F
            | Extension.D
            | Extension.C
            | Extension.ZIFENCEI
            | Extension.ZICSR,
        ),
        ISATestEntry(
            "rv32imafdczifencei_zicsr",
            True,
            32,
            32,
            Extension.I
            | Extension.M
            | Extension.A
            | Extension.F
            | Extension.D
            | Extension.C
            | Extension.ZIFENCEI
            | Extension.ZICSR,
        ),
        ISATestEntry(
            "rv32i_m_a_f_d_c_zifencei_zicsr",
            True,
            32,
            32,
            Extension.I
            | Extension.M
            | Extension.A
            | Extension.F
            | Extension.D
            | Extension.C
            | Extension.ZIFENCEI
            | Extension.ZICSR,
        ),
        ISATestEntry("rv32ec_zicsr", True, 32, 16, Extension.E | Extension.C | Extension.ZICSR),
        ISATestEntry("rv64i", True, 64, 32, Extension.I),
        ISATestEntry(
            "rv64g",
            True,
            64,
            32,
            Extension.I | Extension.M | Extension.A | Extension.F | Extension.D | Extension.ZIFENCEI | Extension.ZICSR,
        ),
        ISATestEntry("rv32", False),
        ISATestEntry("rv32ie", False),
        ISATestEntry("rv64e", False),
        ISATestEntry("rv32fdc", False),
        ISATestEntry("rv32izicsrzmmul", False),
        ISATestEntry("rv64imadc", False),
        ISATestEntry("rvima", False),
        ISATestEntry("rv42i", False),
    ]

    def do_test(self, test):
        def _do_test():
            isa = ISA(test.isa_str)
            self.assertEqual(isa.xlen, test.xlen)
            self.assertEqual(isa.reg_cnt, test.reg_cnt)
            self.assertEqual(isa.extensions, test.extensions)
            self.assertEqual(isa.ilen, 32)

        if not test.valid:
            with self.assertRaises(RuntimeError):
                _do_test()
        else:
            _do_test()

    def test_isa(self):
        for test in self.ISA_TESTS:
            self.do_test(test)
