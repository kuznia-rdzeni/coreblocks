import math
from transactron.testing import *
import random
from transactron.utils.amaranth_ext.hw_hash import *
import pytest


def rot(x, k) -> int:
    return ((x) << (k)) | ((x) >> (32 - (k)))


def lookup3(value, seed):
    if seed is None:
        seed = 0xDEADBEEF
    a = (value & ((1 << 32) - 1)) + seed
    b = ((value >> 32) & ((1 << 32) - 1)) + seed
    c = ((value >> 64) & ((1 << 32) - 1)) + seed

    a &= 0xFFFFFFFF
    b &= 0xFFFFFFFF
    c &= 0xFFFFFFFF
    c ^= b
    c &= 0xFFFFFFFF
    c -= rot(b, 14)
    c &= 0xFFFFFFFF
    a ^= c
    a &= 0xFFFFFFFF
    a -= rot(c, 11)
    a &= 0xFFFFFFFF
    b ^= a
    b &= 0xFFFFFFFF
    b -= rot(a, 25)
    b &= 0xFFFFFFFF
    c ^= b
    c &= 0xFFFFFFFF
    c -= rot(b, 16)
    c &= 0xFFFFFFFF
    a ^= c
    a &= 0xFFFFFFFF
    a -= rot(c, 4)
    a &= 0xFFFFFFFF
    b ^= a
    b &= 0xFFFFFFFF
    b -= rot(a, 14)
    b &= 0xFFFFFFFF
    c ^= b
    c &= 0xFFFFFFFF
    c -= rot(b, 24)
    c &= 0xFFFFFFFF
    return c


@pytest.mark.parametrize("model", [JenkinsHash96Bits, lambda: SipHash64Bits(2, 4), lambda: SipHash64Bits(1, 3)])
@pytest.mark.parametrize("bits", [16, 32, 64, 96])
@pytest.mark.parametrize("seed", [None, 0x573A8CF])
class TestHash(TestCaseWithSimulator):
    test_number = 800
    modulo = 16

    def process(self):
        hash_mod_list = [0] * self.modulo
        if self.seed is not None:
            yield self.circ.seed.eq(self.seed)
        for i in range(self.test_number):
            in_val = random.randrange(1 << self.bits)
            yield self.circ.value.eq(in_val)
            yield Settle()
            yield Delay(1e-9)  # pretty print
            hash_mod_list[(yield self.circ.out_hash) % self.modulo] += 1
        #            hash_mod_list[lookup3(in_val, self.seed) % self.modulo] += 1
        print(hash_mod_list)

        # Chi squere test
        # stat = sum([(count - self.test_number/self.modulo)**2/count for count in hash_mod_list])
        # Chi(15) for p=0.01
        # assert stat < 30.5779

        for count in hash_mod_list:
            p_test = count / self.test_number
            p_expected = 1 / self.modulo

            # Test of proportion
            stat = (p_test - p_expected) / (math.sqrt(p_expected * (1 - p_expected))) * math.sqrt(self.test_number)

            # Assumimg p=0.05 of the whole test and Bonfferoni correction k=16, we need the used p=0.003.
            # For N(0,1) this is circa 3*standard deviation
            # Sadly these hash algorithms have problems for the small input data sizes, so threshold is set on 4
            assert stat < 4 and stat > -4

    def test_random(self, seed, bits, model):
        self.seed = seed
        self.bits = bits
        self.circ = model()
        with self.run_simulation(self.circ) as sim:
            sim.add_process(self.process)
