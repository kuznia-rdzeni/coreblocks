from amaranth import *
from coreblocks.transactions import Method, def_method
from coreblocks.transactions.lib import MemoryBank, Forwarder
from coreblocks.params import *
from coreblocks.params.vector_params import VectorParameters
from coreblocks.fu.vector_unit.v_layouts import RegisterLayouts
from coreblocks.fu.vector_unit.utils import EEW

__all__ = ["VectorRegisterFragment"]


class VectorRegisterFragment(Elaboratable):
    def __init__(self, *, gen_params: GenParams, v_params: VectorParameters):
        self.gen_params = gen_params
        self.v_params = v_params

        self.layouts = RegisterLayouts(self.gen_params, self.v_params)

        self.bank = MemoryBank(data_layout=self.layouts.read_resp, elem_count=self.v_params.elems_in_bank)

        self.eew = Signal(EEW)
        # improvement: move to async memory
        self.byte_mask = Signal(self.v_params.bytes_in_vlen // self.v_params.register_bank_count)

        self.read_req = Method.like(self.bank.read_req)
        self.read_resp = Method.like(self.bank.read_resp)
        self.write = Method(i=self.layouts.write)
        self.initialize = Method()
        self.end_write = Method()
        self.clear = Method()

        self.initialize.add_conflict(self.end_write)

    def expand_mask(self, m: Module, mask: Signal) -> Signal:
        signals = [Signal(self.v_params.elen)]
        for i in reversed(range(self.v_params.bytes_in_elen)):
            s = Signal(self.v_params.elen)
            Method.comb += s.eq(signals[-1] << 8 | Mux(mask[i], 0xFF, 0x00))
            signals.append(s)
        return signals[-1]

    def elaborate(self, platform) -> Module:
        m = Module()

        write_ready = Signal()
        read_ready = Signal()

        mask_forward = Forwarder([("data", self.v_params.bytes_in_elen)])
        m.submodules.mask_forward = mask_forward
        m.submodules.bank = self.bank

        @def_method(m, self.read_req, ready=read_ready)
        def _(arg):
            self.bank.read_req(m, arg)
            mask_forward.write(m, data=self.byte_mask.word_select(arg.addr, self.v_params.bytes_in_elen))

        @def_method(m, self.read_resp)
        def _():
            out = self.bank.read_resp(m)
            out_masked = Signal.like(out)
            mask = mask_forward.read(m)
            expanded_mask = self.expand_mask(m, mask.data)
            Method.comb += out_masked.eq(out | expanded_mask)
            return {"data": out_masked}

        @def_method(m, self.write, ready=write_ready)
        def _(addr, data, mask):
            self.bank.write(m, addr=addr, data=data, mask=mask)
            mask_part = self.byte_mask.word_select(addr, self.v_params.bytes_in_elen)
            m.d.sync += mask_part.eq(mask_part | mask)

        @def_method(m, self.initialize)
        def _(eew: Signal):
            m.d.sync += self.byte_mask.eq(0)
            m.d.sync += self.eew.eq(eew)
            m.d.sync += write_ready.eq(1)
            m.d.sync += read_ready.eq(0)

        @def_method(m, self.end_write)
        def _():
            m.d.sync += write_ready.eq(0)
            m.d.sync += read_ready.eq(1)

        @def_method(m, self.clear)
        def _():
            mask_forward.clear(m)

        return m
