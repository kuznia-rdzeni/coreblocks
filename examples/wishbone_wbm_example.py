from coreblocks.wishbone import *
from transactions import TransactionModule
from transactions.lib import *


# class for manual testing WishboneMaster with transaction interface
class WishboneMasterTransCircuit(Elaboratable):
    def __init__(self):
        self.input = Record(WishboneMaster.requestLayout)
        self.input_btn = Signal()

        self.output = Record(WishboneMaster.resultLayout)
        self.output_btn = Signal()

        self.m = Module()
        self.tm = TransactionModule(self.m)
        self.wbm = WishboneMaster()

        self.ports = [
            self.input.data,
            self.input.addr,
            self.input.we,
            self.input_btn,
            self.output.err,
            self.output.data,
            self.output_btn,
        ] + self.wbm.ports

    def elaborate(self, platform):
        m = self.m
        m.submodules.wmb = self.wbm
        m.submodules.inp = inp = ClickIn(self.input.shape().width)
        m.submodules.out = out = ClickOut(self.output.shape().width)

        m.submodules.idt = ConnectTrans(inp.get, self.wbm.request)
        m.submodules.dot = ConnectTrans(self.wbm.result, out.put)

        m.d.comb += inp.btn.eq(self.input_btn)
        m.d.comb += inp.dat.eq(self.input)
        m.d.comb += self.output.eq(out.dat)
        m.d.comb += out.btn.eq(self.output_btn)

        return self.tm


if __name__ == "__main__":
    from amaranth.back import verilog

    model = WishboneMasterTransCircuit()
    with open("wishbone_master_trans.v", "w") as f:
        f.write(verilog.convert(model, ports=model.ports))
