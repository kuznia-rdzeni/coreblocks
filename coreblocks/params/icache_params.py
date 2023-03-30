from amaranth.utils import log2_int


class ICacheParameters:
    """Parameters of the Instruction Cache.

    Parameters
    ----------
    addr_width : int
        Length of addresses used in the cache (in bits).
    word_width : int
        Length of the machine word (in bits).
    num_of_ways : int
        Associativity of the cache.
    num_of_sets : int
        Number of cache sets.
    block_size_bytes : int
        The size of a single cache block in bytes.
    """

    def __init__(self, *, addr_width, word_width, num_of_ways, num_of_sets, block_size_bytes):
        self.addr_width = addr_width
        self.word_width = word_width
        self.num_of_ways = num_of_ways
        self.num_of_sets = num_of_sets
        self.block_size_bytes = block_size_bytes

        # We are sanely assuming that the instruction width is 4 bytes.
        self.instr_width = 32

        self.word_width_bytes = word_width // 8

        def is_power_of_two(n):
            return (n != 0) and (n & (n - 1) == 0)

        if block_size_bytes % self.word_width_bytes != 0:
            raise ValueError("block_size_bytes must be divisble by the machine word size")
        if self.num_of_ways not in {1, 2, 4, 8}:
            raise ValueError(f"num_of_ways must be 1, 2, 4 or 8, not {num_of_ways}")
        if not is_power_of_two(num_of_sets):
            raise ValueError(f"num_of_sets must be a power of 2, not {num_of_sets}")
        if not is_power_of_two(block_size_bytes) or block_size_bytes < 4:
            raise ValueError(f"block_size_bytes must be a power of 2 and not smaller than 4, not {block_size_bytes}")

        self.offset_bits = log2_int(self.block_size_bytes)
        self.index_bits = log2_int(self.num_of_sets)
        self.tag_bits = self.addr_width - self.offset_bits - self.index_bits

        self.index_start_bit = self.offset_bits
        self.index_end_bit = self.offset_bits + self.index_bits - 1

        self.words_in_block = self.block_size_bytes // self.word_width_bytes
