from amaranth import *
from coreblocks.transactions import *
from coreblocks.transactions.core import *
from coreblocks.transactions.lib import MemoryBank
from coreblocks.params import *
from coreblocks.utils.fifo import BasicFifo
from coreblocks.params.vector_params import VectorParameters
from coreblocks.fu.vector_unit.v_layouts import VectorRegisterBankLayouts
from coreblocks.fu.vector_unit.utils import EEW

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

        self.bank = MemoryBank(
            data_layout=self.layouts.read_resp, elem_count=self.v_params.elems_in_bank, granularity=8
        )

        self.eew = Signal(EEW)
        # improvement: move to async memory
        self.byte_mask = Signal(self.v_params.bytes_in_vlen // self.v_params.register_bank_count)

        self.read_req = Method.like(self.bank.read_req, name="read_req")
        self.read_resp = Method.like(self.bank.read_resp, name="read_resp")
        self.write = Method(i=self.layouts.write)
        self.write_scalar = Method()
        self.write_mask = Method()
        self.initialise = Method(i=self.layouts.initialize)
        self.clear = Method()

        self.initialise.add_conflict(self.read_req, Priority.LEFT)
        self.initialise.add_conflict(self.read_resp, Priority.LEFT)
        self.initialise.add_conflict(self.write, Priority.LEFT)
        self.clear.add_conflict(self.read_req, Priority.LEFT)
        self.clear.add_conflict(self.read_resp, Priority.LEFT)
        self.clear.add_conflict(self.write, Priority.LEFT)
        self.clear.add_conflict(self.initialise, Priority.LEFT)

    def expand_mask(self, mask: Value) -> Value:
        return Cat(Mux(mask[i], 0xFF, 0x00) for i in range(self.v_params.bytes_in_elen))

    def elaborate(self, platform) -> TModule:
        m = TModule()

        mask_forward = BasicFifo([("data", self.v_params.bytes_in_elen)], 2)
        m.submodules.mask_forward = mask_forward
        m.submodules.bank = self.bank

        @def_method(m, self.read_req)
        def _(arg):
            self.bank.read_req(m, arg)
            mask_forward.write(m, data=self.byte_mask.word_select(arg.addr, self.v_params.bytes_in_elen))

        @def_method(m, self.read_resp)
        def _():
            out = self.bank.read_resp(m)
            mask = mask_forward.read(m)
            out_masked = Signal.like(out)
            expanded_mask = ~self.expand_mask(mask.data)
            m.d.top_comb += out_masked.eq(out | expanded_mask)
            return {"data": out_masked}

        @def_method(m, self.write)
        def _(addr, data, mask):
            self.bank.write(m, addr=addr, data=data, mask=mask)
            mask_part = self.byte_mask.word_select(addr, self.v_params.bytes_in_elen)
            m.d.sync += mask_part.eq(mask_part | mask)

        @def_method(m, self.initialise)
        def _(eew: Signal):
            m.d.sync += self.byte_mask.eq(0)
            m.d.sync += self.eew.eq(eew)
            mask_forward.clear(m)

        @def_method(m, self.clear)
        def _():
            mask_forward.clear(m)

        @def_method(m, self.write_scalar)
        def _():
            pass

        return m
