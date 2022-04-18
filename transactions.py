from contextlib import contextmanager
from functools import reduce
from operator import and_

from amaranth import *

class Transaction:
    def __init__(self, m : Module):
        self.m = m

        self.methods = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        methods, valid_signals = zip(*self.methods)
        ready_signals = [m.ready for m in methods]

        all_valid = reduce(and_, valid_signals, 1)

        for method in methods:
            rem_ready = [r for r in ready_signals if r is not method.ready]
            rest_ready = reduce(and_, rem_ready, 1)

            self.m.d.comb += method.run.eq(all_valid & rest_ready)

    def add_method(self, method, valid):
        self.methods.append((method, valid))

class Method:
    def __init__(self, data_in=[], data_out=[]):
        self.run = Signal()
        self.ready = Signal()
        self.data_in = Record(data_in)
        self.data_out = Record(data_out)

    @contextmanager
    def when_called(self, m : Module, rdy=C(1), ret=C(0)):
        m.d.comb += self.ready.eq(rdy)
        m.d.comb += self.data_out.eq(ret)
        with m.If(self.run & self.ready):
            yield self.data_in

    def call(self, t : Transaction, run=C(1), arg=C(0)):
        t.m.d.comb += self.data_in.eq(arg)
        t.add_method(self, run)
        return self.data_out

# "Clicked" input

class OpIn(Elaboratable):
    def __init__(self, width=1):
        self.btn = Signal()
        self.dat = Signal(width)

        self.if_get = Method(data_out=[('data', width)])

    def elaborate(self, platform):
        m = Module()

        btn1 = Signal()
        btn2 = Signal()
        dat1 = Signal.like(self.dat)
        m.d.sync += btn1.eq(self.btn)
        m.d.sync += btn2.eq(btn1)
        m.d.sync += dat1.eq(self.dat)

        op_rdy = Signal()
        ret_data = Signal.like(self.dat)

        with self.if_get.when_called(m, rdy=op_rdy, ret=ret_data):
            m.d.sync += op_rdy.eq(0)

        with m.If(~btn2 & btn1):
            m.d.sync += op_rdy.eq(1)
            m.d.sync += ret_data.eq(dat1)

        return m

# "Clicked" output

class OpOut(Elaboratable):
    def __init__(self, width=1):
        self.btn = Signal()
        self.dat = Signal(width)

        self.if_put = Method(data_in=[('data', width)])

    def elaborate(self, platform):
        m = Module()

        btn1 = Signal()
        btn2 = Signal()
        m.d.sync += btn1.eq(self.btn)
        m.d.sync += btn2.eq(btn1)

        with self.if_put.when_called(m, rdy=(~btn2 & btn1)) as arg:
            m.d.sync += self.dat.eq(arg.data)

        return m

import amaranth.lib.fifo

class OpFIFO(Elaboratable):
    def __init__(self, width, depth):
        self.width = width
        self.depth = depth

        self.entry_layout = [('data', width)]

        self.if_read = Method(data_out=self.entry_layout)
        self.if_write = Method(data_in=self.entry_layout)
   
    def elaborate(self, platform):
        m = Module()

        m.submodules.fifo = fifo = amaranth.lib.fifo.SyncFIFO(width=self.width, depth=self.depth)

        with self.if_write.when_called(m, rdy=fifo.w_rdy) as arg:
            m.d.comb += fifo.w_en.eq(1)
            m.d.comb += fifo.w_data.eq(arg.data)

        data_packed = Record(self.entry_layout)
        m.d.comb += data_packed.data.eq(fifo.r_data)
        with self.if_read.when_called(m, rdy=fifo.r_rdy, ret=data_packed):
            m.d.comb += fifo.r_en.eq(1)

        return m

class CopyTrans(Elaboratable):
    def __init__(self, src, dst):
        self.src = src
        self.dst = dst

    def elaborate(self, platform):
        m = Module()

        with Transaction(m) as t:
            data = self.src.if_read.call(t)

            data_packed = Record(self.src.entry_layout)
            m.d.comb += data_packed.data.eq(data)
            self.dst.if_put.call(t, arg=data_packed)

        return m

class CatTrans(Elaboratable):
    def __init__(self, src1, src2, dst):
        self.src1 = src1
        self.src2 = src2
        self.dst = dst

    def elaborate(self, platform):
        m = Module()

        with Transaction(m) as t:
            data1 = self.src1.if_get.call(t)
            data2 = self.src2.if_get.call(t)

            data_packed = Record(self.dst.entry_layout)
            m.d.comb += data_packed.data.eq(Cat(data1.data, data2.data))
            self.dst.if_write.call(t, arg=data_packed)

        return m

class SimpleCircuit(Elaboratable):
    def __init__(self):
        fifo = OpFIFO(2, 16)
        in1 = OpIn()
        in2 = OpIn()
        out = OpOut(2)
        self.submodules = {
            'fifo': fifo,
            'in1': in1, 'in2': in2, 'out': out,
            'cti': CatTrans(in1, in2, fifo),
            'cto': CopyTrans(fifo, out)
        }
        self.ports = [in1.btn, in1.dat, in2.btn, in2.dat, out.btn, out.dat]

    def elaborate(self, platform):
        m = Module()

        for k, v in self.submodules.items():
            m.submodules[k] = v

        return m

if __name__ == "__main__":
    from amaranth.back import verilog
    import os
    model = SimpleCircuit()
    with open("result.v", "w") as f:
        f.write(verilog.convert(model, ports=model.ports))
