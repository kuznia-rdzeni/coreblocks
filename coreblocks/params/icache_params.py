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
    line_bytes_log : int
        Log of the size of a single cache line in bytes.
    enable : bool
        Enable the instruction cache. If disabled, requestes are bypassed to the bus.
    """

    def __init__(
        self,
        *,
        addr_width,
        word_width,
        fetch_block_bytes_log,
        num_of_ways,
        num_of_sets_bits,
        line_bytes_log,
        enable=True
    ):
        self.addr_width = addr_width
        self.word_width = word_width
        self.fetch_block_bytes_log = fetch_block_bytes_log
        self.num_of_ways = num_of_ways
        self.num_of_sets_bits = num_of_sets_bits
        self.line_bytes_log = line_bytes_log
        self.enable = enable
        self.fetch_block_bytes = 2**fetch_block_bytes_log
        self.num_of_sets = 2**num_of_sets_bits
        self.line_size_bytes = 2**line_bytes_log

        self.word_width_bytes = word_width // 8

        self.offset_bits = line_bytes_log
        self.index_bits = num_of_sets_bits
        self.tag_bits = self.addr_width - self.offset_bits - self.index_bits

        self.index_start_bit = self.offset_bits
        self.index_end_bit = self.offset_bits + self.index_bits - 1

        self.words_in_line = self.line_size_bytes // self.word_width_bytes
        self.words_in_fetch_block = self.fetch_block_bytes // self.word_width_bytes
        self.fetch_blocks_in_line = self.line_size_bytes // self.fetch_block_bytes

        if not enable:
            return

        if line_bytes_log < self.fetch_block_bytes_log:
            raise ValueError("The instruction cache line size must be not smaller than the fetch block size.")
