
from amaranth import *
from . import *
from .lib import *

class SimpleCircuit(Elaboratable):
    def __init__(self):
        self.in1_btn = Signal()
        self.in1_dat = Signal()
        self.in2_btn = Signal()
        self.in2_dat = Signal()
        self.out_btn = Signal()
        self.out_dat = Signal(2)
        self.ports = [self.in1_btn, self.in1_dat, self.in2_btn, self.in2_dat, self.out_btn, self.out_dat]

    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        with tm.transactionContext():
            m.submodules.fifo = fifo = FIFO(2, 16)
            m.submodules.in1 = in1 = ClickIn()
            m.submodules.in2 = in2 = ClickIn()
            m.submodules.out = out = ClickOut(2)
            m.submodules.cti = CatTrans(in1.get, in2.get, fifo.write)
            m.submodules.cto = ConnectTrans(fifo.read, out.put)
            m.d.comb += in1.btn.eq(self.in1_btn)
            m.d.comb += in2.btn.eq(self.in2_btn)
            m.d.comb += out.btn.eq(self.out_btn)
            m.d.comb += in1.dat.eq(self.in1_dat)
            m.d.comb += in2.dat.eq(self.in2_dat)
            m.d.comb += self.out_dat.eq(out.dat)

        return tm

if __name__ == "__main__":
    from amaranth.back import verilog
    import os
    model = SimpleCircuit()
    with open("result.v", "w") as f:
        f.write(verilog.convert(model, ports=model.ports))

