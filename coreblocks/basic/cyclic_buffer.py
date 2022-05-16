from amaranth import *

import math

class CyclicBuffer(Elaboratable):
    """
    A cyclic buffer holding maximum of [size] elements, each [dataWidth] bits wide. Elements can be indexed with numbers of [self.idWidth] width.
    """
    def __init__(self, size, dataWidth):
        self.size = size
        self.dataWidth = dataWidth

        #* Derived parameters
        self.idWidth = math.ceil(math.log2(size))

        #* Ports
        self.en  = Signal()

        #** insert
        self.insert_start = Signal()              # in
        self.insert_data = Signal(self.dataWidth) # in
        self.insert_id = Signal(self.idWidth)     # out
        self.insert_ready = Signal()              # out

        #** update
        self.update_start = Signal()              # in
        self.update_id = Signal(self.idWidth)     # in
        self.update_data = Signal(self.dataWidth) # in

        #** last
        self.last_id = Signal(self.idWidth) # out
        self.last_valid = Signal()     # out

        #** deleteLast
        # possible whenever not empty
        self.delete_last_start = Signal() # in

        #** peek
        # [peek_data] will remain valid until it's overwritten by [insert] or [update].
        self.peek_id = Signal()                 # in
        self.peek_data = Signal(self.dataWidth) # out

        #* State
        self.isEmpty = Signal()
        self.first = Signal(self.idWidth)
        self.last = Signal(self.idWidth)

        self.data = Memory(width = self.dataWidth, depth = self.size) # no init

        self.dummy = Signal(16) # remove me

    def elaborate(self, platform):
        m = Module()

        with m.If(self.en):
            m.d.sync += self.dummy.eq(self.dummy + 1)

        return m
