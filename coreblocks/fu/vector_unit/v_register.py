from amaranth import *
from coreblocks.transactions.core import *
from coreblocks.transactions.lib import MemoryBank
from coreblocks.params import *
from coreblocks.utils.fifo import BasicFifo
from coreblocks.fu.vector_unit.v_layouts import VectorRegisterBankLayouts
from coreblocks.fu.vector_unit.utils import *

__all__ = ["VectorRegisterBank"]


class VectorRegisterBank(Elaboratable):
    """Bank of vector register file

    This module implements a one bank of vector register file. It has one input
    port and one output port. Each element in the bank always has ELEN bits. When
    EEW indicates that there are more elements in an ELEN word, then they are ordered
    on little endian, so the first element is on the first byte.

    Masks are also in little-endian form, so the first bit is for the first element,
    the second bit for the second element, and so on.

    Attrubutes
    ----------
    read_req : Method
        Method to issue a read request, with the `MemoryBank.read_req` layout.
    read_resp : Method
        Method to receive a read response for a previously issued request. It returns
        ELEN bits for each request. Any byte, that hasn't been written before
        will be returned in mask agnostic way, so overwritten with 1's.
    write : Method
        Method for writing data to register. Mask has `ELEN//8` bits and each bit
        indicates if the corresponding byte is valid.
    initialise : Method
        Method to initialise the content of the bank before writing new data into it.
    clear : Method
        Clear register and all internal buffers.
    """

    def __init__(self, *, gen_params: GenParams):
        self.gen_params = gen_params
        self.v_params = self.gen_params.v_params

        self.layouts = VectorRegisterBankLayouts(self.gen_params)

        # improvement: move to async memory
        self.byte_mask = Signal(self.v_params.bytes_in_vlen // self.v_params.register_bank_count)

        self.read_req = Method(i=self.layouts.read_req, name="read_req")
        self.read_resp = Method(o=self.layouts.read_resp, name="read_resp")
        self.write = Method(i=self.layouts.write)
        self.write_scalar = Method()
        self.write_mask = Method()
        self.initialise = Method(i=self.layouts.initialise)
        self.clear = Method()

    def elaborate(self, platform) -> TModule:
        m = TModule()

        resp_ready = Signal()

        data_mem = Memory(width = self.v_params.elen, depth = self.v_params.elens_in_bank)
        # we have either bunch of writes or reads. Reads and writes can not be send interchangable
        # so we can hav transparent=False
        m.submodules.read_port = read_port = data_mem.read_port(transparent=False) 
        m.submodules.write_port = write_port = data_mem.write_port(granularity=8)

        mask_forward = BasicFifo([("data", self.v_params.bytes_in_elen)], 2)
        m.submodules.mask_forward = mask_forward


        @def_method(m, self.read_resp, resp_ready)
        def _():
            mask = mask_forward.read(m)
            out_masked = Signal(self.v_params.elen)
            expanded_mask = ~expand_mask(self.v_params, mask.data)
            m.d.top_comb += out_masked.eq(read_port.data | expanded_mask)
            # Use enable signal to don't store last address in local register
            m.d.sync += resp_ready.eq(0)
            return {"data": out_masked}

        # Schedule before allow us to don't have a support memory for the previously read
        # data, so we optimise resource usage at the cost of critical path
        self.read_resp.schedule_before(self.read_req)
        @def_method(m, self.read_req, ~resp_ready | self.read_resp.run)
        def _(addr):
            m.d.top_comb += read_port.addr.eq(addr)
            m.d.comb += read_port.en.eq(1)
            m.d.sync += resp_ready.eq(1)
            mask_forward.write(m, data=self.byte_mask.word_select(addr, self.v_params.bytes_in_elen))

        @def_method(m, self.write)
        def _(addr, data, valid_mask):
            m.d.top_comb += write_port.addr.eq(addr)
            m.d.top_comb += write_port.data.eq(data)
            m.d.comb += write_port.en.eq(valid_mask)
            mask_part = self.byte_mask.word_select(addr, self.v_params.bytes_in_elen)
            m.d.sync += mask_part.eq(mask_part | valid_mask)

        @def_method(m, self.initialise)
        def _():
            m.d.sync += self.byte_mask.eq(0)
            mask_forward.clear(m)

        @def_method(m, self.clear)
        def _():
            mask_forward.clear(m)

        @def_method(m, self.write_scalar)
        def _():
            pass

        return m
