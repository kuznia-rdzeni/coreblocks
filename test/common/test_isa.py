import pytest
import unittest

from coreblocks.arch.isa import Extension, ISA
from dataclasses import dataclass


class TestISA(unittest.TestCase):
    @dataclass
    class ISATestEntry:
        exts_in: Extension
        valid: bool
        xlen: int | None = None
        reg_cnt: int | None = None
        extensions: Extension | None = None

    ISA_TESTS = [
        ISATestEntry(Extension.I, True, 32, 32, Extension.I),
        ISATestEntry(
            Extension.I | Extension.M | Extension.A,
            True,
            32,
            32,
            Extension.I | Extension.M | Extension.ZMMUL | Extension.A | Extension.ZAAMO | Extension.ZALRSC,
        ),
        ISATestEntry(
            Extension.I | Extension.M | Extension.A | Extension.F | Extension.D | Extension.C | Extension.ZICSR,
            True,
            32,
            32,
            Extension.I
            | Extension.M
            | Extension.A
            | Extension.ZAAMO
            | Extension.ZALRSC
            | Extension.F
            | Extension.D
            | Extension.C
            | Extension.ZCA
            | Extension.ZCF
            | Extension.ZCD
            | Extension.ZICSR
            | Extension.ZMMUL,
        ),
        ISATestEntry(
            Extension.I | Extension.M | Extension.F,
            True,
            32,
            32,
            Extension.I | Extension.M | Extension.F | Extension.ZICSR | Extension.ZMMUL,
        ),
        ISATestEntry(
            Extension.I | Extension.ZICSR,
            True,
            32,
            32,
            Extension.I | Extension.ZICSR,
        ),
        ISATestEntry(
            Extension.I | Extension.M | Extension.C | Extension.ZICSR,
            True,
            32,
            32,
            Extension.I | Extension.M | Extension.ZMMUL | Extension.C | Extension.ZCA | Extension.ZICSR,
        ),
        ISATestEntry(
            Extension.I | Extension.ZMMUL,
            True,
            32,
            32,
            Extension.I | Extension.ZMMUL,
        ),
        ISATestEntry(
            Extension.I
            | Extension.M
            | Extension.A
            | Extension.F
            | Extension.D
            | Extension.C
            | Extension.ZIFENCEI
            | Extension.ZICSR,
            True,
            32,
            32,
            Extension.I
            | Extension.M
            | Extension.ZMMUL
            | Extension.A
            | Extension.ZAAMO
            | Extension.ZALRSC
            | Extension.F
            | Extension.D
            | Extension.C
            | Extension.ZCA
            | Extension.ZCF
            | Extension.ZCD
            | Extension.ZIFENCEI
            | Extension.ZICSR,
        ),
        ISATestEntry(
            Extension.E | Extension.C | Extension.ZICSR,
            True,
            32,
            16,
            Extension.E | Extension.C | Extension.ZCA | Extension.ZICSR,
        ),
        ISATestEntry(Extension.I, True, 64, 32, Extension.I),
        ISATestEntry(
            Extension.G,
            True,
            64,
            32,
            Extension.I
            | Extension.M
            | Extension.ZMMUL
            | Extension.A
            | Extension.ZAAMO
            | Extension.ZALRSC
            | Extension.F
            | Extension.D
            | Extension.ZIFENCEI
            | Extension.ZICSR,
        ),
        ISATestEntry(Extension.I | Extension.E, True, 32, 32, Extension.I | Extension.E),
        ISATestEntry(Extension(0), False, 32),
        ISATestEntry(Extension.E, False, 64),
        ISATestEntry(Extension.F | Extension.D | Extension.C, False, 32),
        ISATestEntry(Extension.I, False, 42),
    ]

    def do_test(self, test):
        def _do_test():
            print(f"{test}")
            isa = ISA(test.exts_in, test.xlen)
            assert isa.xlen == test.xlen
            assert isa.reg_cnt == test.reg_cnt
            assert isa.extensions == test.extensions
            assert isa.ilen == 32

        if not test.valid:
            with pytest.raises(RuntimeError):
                _do_test()
        else:
            _do_test()

    def test_isa(self):
        for test in self.ISA_TESTS:
            self.do_test(test)
