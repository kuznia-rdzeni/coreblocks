from amaranth import *

__all__ = ["PseudoRandomGenerator"]


class PseudoRandomGenerator(Elaboratable):
    """Deterministic replacement randomness from a 65535-state Galois LFSR."""

    def __init__(self, width: int):
        if not 1 <= width <= 16:
            raise ValueError("Pseudo-random output width must be between 1 and 16 bits")
        self.value = Signal(width)
        self.advance = Signal()

    def elaborate(self, platform):
        m = Module()
        state = Signal(16, init=0xACE1)
        m.d.comb += self.value.eq(state[: len(self.value)])
        with m.If(self.advance):
            m.d.sync += state.eq((state >> 1) ^ Mux(state[0], C(0xB400, 16), C(0, 16)))
        return m
