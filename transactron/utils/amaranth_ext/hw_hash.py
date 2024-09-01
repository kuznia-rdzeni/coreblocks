from amaranth import *
from transactron.utils._typing import ValueLike
from typing import Optional
from transactron.utils.assign import add_to_submodules
from transactron.utils._typing import ModuleLike

__all__ = ["JenkinsHash96Bits", "SipHash64Bits"]


class JenkinsHash96Bits(Elaboratable):
    """
    Simplified implementation of the Lookup3 hash function.

    The Lookup3 function is a non-cryptographic hash function that can be used in hash tables and sketches.
    By default it supports arbitrary length input, but this implementation is simplified and
    only the last step of the Lookup3 is implemented, which means that no more than 96 bits can be hashed.
    Provided implementation is combinational, so it works in one cycle.
    All unused bits should be bound to 0.

    Implementation based on:
    https://chromium.googlesource.com/external/smhasher/+/5b8fd3c31a58b87b80605dca7a64fad6cb3f8a0f/lookup3.cpp

    Parameters
    ----------
    seed : Signal(32)
        The seed to use when hashing. By default it is a constant chosen randomly.
        You can override it to get different hash values using the same algorithm.
    value : Signal(96)
        The input value to be hashed. Unused bits should be 0.
    out_hash : Signal(32)
        The calculated hash.
    """

    def __init__(self):
        self.seed = Signal(32, reset=0x70736575)  # Default value chosen randomly
        self.value = Signal(96)
        self.out_hash = Signal(32)

    def _finalize(self, m: Module, a: Value, b: Value, c: Value):
        a_tmp1 = Signal(32)
        b_tmp1 = Signal(32)
        c_tmp1 = Signal(32)
        a_tmp2 = Signal(32)
        b_tmp2 = Signal(32)
        c_tmp2 = Signal(32)
        c_tmp3 = Signal(32)

        m.d.comb += [
            c_tmp1.eq((c ^ b) - b.rotate_left(14)),
            a_tmp1.eq((a ^ c_tmp1) - c_tmp1.rotate_left(11)),
            b_tmp1.eq((b ^ a_tmp1) - a_tmp1.rotate_left(25)),
            c_tmp2.eq((c_tmp1 ^ b_tmp1) - b_tmp1.rotate_left(16)),
            a_tmp2.eq((a_tmp1 ^ c_tmp2) - c_tmp2.rotate_left(4)),
            b_tmp2.eq((b_tmp1 ^ a_tmp2) - a_tmp2.rotate_left(14)),
            c_tmp3.eq((c_tmp2 ^ b_tmp2) - b_tmp2.rotate_left(24)),
        ]
        return c_tmp3

    def elaborate(self, platform):
        m = Module()

        a = Signal(32)
        b = Signal(32)
        c = Signal(32)
        m.d.comb += a.eq(self.value[0:32] + self.seed)
        m.d.comb += b.eq(self.value[32:64] + self.seed)
        m.d.comb += c.eq(self.value[64:96] + self.seed)

        m.d.comb += self.out_hash.eq(self._finalize(m, a, b, c))

        return m

    @staticmethod
    def create(
        m: ModuleLike,
        input: ValueLike,
        name: Optional[str] = None,
    ) -> Signal:
        """Syntax sugar for JenkinsHash96Bits creation

        This function is equivalent to:

        .. highlight:: python
        .. code-block:: python

            hw_block = JenkinsHash96Bits()
            add_to_submodules(m, hw_block, name)
            m.d.comb += hw_block.value.eq(input)
            return hw_block.out_hash

        """
        hw_block = JenkinsHash96Bits()
        add_to_submodules(m, hw_block, name)
        m.d.comb += hw_block.value.eq(input)
        return hw_block.out_hash


class SipHash64Bits(Elaboratable):
    """Simplified implementation of SipHash

    This is a simplified implementation of SipHash. It assumes that no more than
    64 bits are being hashed. It also doesn't use the last word added to the
    hash by SipHash, which contains length (because length is always 4).
    These changes allow for faster and cheaper hash computation.

    Implementation based on:
    https://eprint.iacr.org/2012/351.pdf

    Parameters
    ----------
    seed : Signal(128)
        The seed to use when hashing. By default it is a constant chosen randomly.
        You can override it to get different hash values using the same algorithm.
    value : Signal(64)
        The input value to be hashed. Unused bits should be 0.
    out_hash : Signal(64)
        The calculated hash.
    """

    def __init__(self, c: int = 2, d: int = 4):
        """
        The default parameters are set to implement SipHash-2-4, which is secure
        according to the SipHash authors. Software which currently uses SipHash
        tends to use the weaker and faster version SipHash-1-3 (e.g. Python 3.11).

        Parameters
        ----------
        c : int
            Number of the SipRound layers in the inner part of mixing.
        d : int
            Number of the SipRound layers in the finalize part of mixing.
        """
        self.seed = Signal(128, reset=0x8FE1A3B9D43A725CDDB65E9FBBD79951)  # Randomly chosen constant
        self.value = Signal(64)
        self.out_hash = Signal(64)
        self.mixing_layers = c
        self.finalize_layers = d

    def _sip_round(self, m, v0, v1, v2, v3):
        v0_tmp1 = Signal(64)
        v1_tmp1 = Signal(64)
        v2_tmp1 = Signal(64)
        v3_tmp1 = Signal(64)
        v0_tmp2 = Signal(64)
        v1_tmp2 = Signal(64)
        v2_tmp2 = Signal(64)
        v3_tmp2 = Signal(64)

        m.d.comb += [
            v0_tmp1.eq(v0 + v1),
            v1_tmp1.eq(v0_tmp1 ^ v1.rotate_left(13)),
            v2_tmp1.eq(v2 + v3),
            v3_tmp1.eq(v2_tmp1 ^ v3.rotate_left(16)),
            v0_tmp2.eq(v0_tmp1.rotate_left(32) + v3_tmp1),
            v2_tmp2.eq(v2_tmp1 + v1_tmp1),
            v1_tmp2.eq(v1_tmp1.rotate_left(17) ^ v2_tmp2),
            v3_tmp2.eq(v3_tmp1.rotate_left(21) ^ v0_tmp2),
        ]

        return v0_tmp2, v1_tmp2, v2_tmp2.rotate_left(32), v3_tmp2

    def elaborate(self, platform) -> Module:
        m = Module()

        v0 = self.seed[0:64] ^ 0x736F6D6570736575
        v1 = self.seed[64:128] ^ 0x646F72616E646F6D
        v2 = self.seed[0:64] ^ 0x6C7967656E657261
        v3 = self.seed[64:128] ^ 0x7465646279746573 ^ self.value

        for i in range(self.mixing_layers):
            v0, v1, v2, v3 = self._sip_round(m, v0, v1, v2, v3)

        v0 = v0 ^ self.value
        v2 = v2 ^ 0xFF

        for i in range(self.finalize_layers):
            v0, v1, v2, v3 = self._sip_round(m, v0, v1, v2, v3)
        m.d.comb += self.out_hash.eq(v0 ^ v1 ^ v2 ^ v3)

        return m

    @staticmethod
    def create(
        m: ModuleLike,
        input: ValueLike,
        c: int = 2,
        d: int = 4,
        name: Optional[str] = None,
    ) -> Signal:
        """Syntax sugar for SipHash64Bits creation

        This function is equivalent to:

        .. highlight:: python
        .. code-block:: python

            hw_block = SipHash64Bits(c=c, d=d)
            add_to_submodules(m, hw_block, name)
            m.d.comb += hw_block.value.eq(input)
            return hw_block.out_hash

        """
        hw_block = SipHash64Bits(c=c, d=d)
        add_to_submodules(m, hw_block, name)
        m.d.comb += hw_block.value.eq(input)
        return hw_block.out_hash
