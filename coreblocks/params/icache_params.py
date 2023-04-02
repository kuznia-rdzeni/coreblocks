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
    num_of_sets_bits : int
        Log of the number of cache sets.
    block_size_bits : int
        Log of the size of a single cache block in bytes.
    """

    def __init__(self, *, addr_width, word_width, num_of_ways, num_of_sets_bits, block_size_bits):
        self.addr_width = addr_width
        self.word_width = word_width
        self.num_of_ways = num_of_ways
        self.num_of_sets_bits = num_of_sets_bits
        self.num_of_sets = 2**num_of_sets_bits
        self.block_size_bits = block_size_bits
        self.block_size_bytes = 2**block_size_bits

        # We are sanely assuming that the instruction width is 4 bytes.
        self.instr_width = 32

        self.word_width_bytes = word_width // 8

        if self.block_size_bytes % self.word_width_bytes != 0:
            raise ValueError("block_size_bytes must be divisble by the machine word size")

        self.offset_bits = block_size_bits
        self.index_bits = num_of_sets_bits
        self.tag_bits = self.addr_width - self.offset_bits - self.index_bits

        self.index_start_bit = self.offset_bits
        self.index_end_bit = self.offset_bits + self.index_bits - 1

        self.words_in_block = self.block_size_bytes // self.word_width_bytes
