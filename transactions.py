from contextlib import contextmanager
from functools import reduce, wraps
from operator import and_

from amaranth import *

class Transaction:
    current = None

    def __init__(self, m : Module):
        self.m = m
        self.methods = []

    def __enter__(self):
        if self.__class__.current is not None:
            raise RuntimeError("Transaction inside transaction")
        self.__class__.current = self
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        methods, valid_signals = zip(*self.methods)
        ready_signals = [m.ready for m in methods]

        all_valid = reduce(and_, valid_signals, 1)

        for method in methods:
            rem_ready = [r for r in ready_signals if r is not method.ready]
            rest_ready = reduce(and_, rem_ready, 1)

            self.m.d.comb += method.run.eq(all_valid & rest_ready)

        self.__class__.current = None

    @classmethod
    def get(cls):
        if cls.current is None:
            raise RuntimeError("No current transaction")
        return cls.current

    def add_method(self, method, valid):
        self.methods.append((method, valid))

class Method:
    def __init__(self, fn, in_layout, out_layout):
        self.fn = fn
        self.run = Signal()
        self.ready = Signal()
        self.input = Record(in_layout)
        self.output = Record(out_layout)

class WithInterface:
    def __init__(self):
        self.methods = []
        self.finalization_ctx = None

        for field in dir(self):
            attr = getattr(self, field)
            if hasattr(attr, 'interface_method'):
                i, o = attr.layout_getter(self)
                self.register_method(attr, i, o)

    def register_method(self, fn, i=[], o=[]):
        method = Method(fn, i, o)

        def wrapper(run=C(1), **kwargs):
            trans = Transaction.get()
            trans.add_method(method, run)
            
            for k, v in kwargs.items():
                trans.m.d.comb += method.input.__getattr__(k).eq(v)

            return method.output

        setattr(self, fn.__name__, wrapper)

        self.methods.append(method)

    def finalize(self, m):
        for method in self.methods:
            kwargs = {}
            for e in method.input.layout:
                kwargs[e[0]] = method.input.__getattr__(e[0])

            self.finalization_ctx = (method, m)
            rdy, ret_val = method.fn(m, **kwargs)
            self.finalization_ctx = None

            for k, v in ret_val.items():
                m.d.comb += method.output.__getattr__(k).eq(v)

            m.d.comb += method.ready.eq(rdy)

    @contextmanager
    def with_guard(self):
        if self.finalization_ctx is None:
            raise RuntimeError("No current finalization context")
        method, m = self.finalization_ctx
        with m.If(method.run & method.ready):
            yield

# "Clicked" input

def interface_method(layout_getter):
    def decorator(func):
        func.interface_method = True
        func.layout_getter = layout_getter
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator

class OpIn(Elaboratable, WithInterface):
    def __init__(self, width=1):
        self.width = width

        self.btn = Signal()
        self.dat = Signal(width)

        self.op_rdy = Signal()
        self.ret_data = Signal(width)

        WithInterface.__init__(self)

    @interface_method(lambda self: ([], [('data', self.width)]))
    def if_get(self, m):
        with self.with_guard():
            m.d.sync += self.op_rdy.eq(0)
        return self.op_rdy, {'data': self.ret_data}

    def elaborate(self, platform):
        m = Module()

        btn1 = Signal()
        btn2 = Signal()
        dat1 = Signal.like(self.dat)
        m.d.sync += btn1.eq(self.btn)
        m.d.sync += btn2.eq(btn1)
        m.d.sync += dat1.eq(self.dat)

        with m.If(~btn2 & btn1):
            m.d.sync += self.op_rdy.eq(1)
            m.d.sync += self.ret_data.eq(dat1)

        self.finalize(m)
        return m

# "Clicked" output

class OpOut(Elaboratable, WithInterface):
    def __init__(self, width=1):
        self.width = width

        self.btn = Signal()
        self.dat = Signal(width)

        self.op_rdy = Signal()

        WithInterface.__init__(self)

    @interface_method(lambda self: ([('data', self.width)], []))
    def if_put(self, m, data):
        with self.with_guard():
            m.d.sync += self.dat.eq(data)
        return self.op_rdy, {}

    def elaborate(self, platform):
        m = Module()

        btn1 = Signal()
        btn2 = Signal()
        m.d.sync += btn1.eq(self.btn)
        m.d.sync += btn2.eq(btn1)
        m.d.comb += self.op_rdy.eq(~btn2 & btn1)

        self.finalize(m)
        return m

import amaranth.lib.fifo

class OpFIFO(Elaboratable, WithInterface):
    def __init__(self, width, depth):
        self.width = width
        self.depth = depth

        self.fifo = amaranth.lib.fifo.SyncFIFO(width=self.width, depth=self.depth)

        WithInterface.__init__(self)

    @interface_method(lambda self: ([], [('data', self.width)]))
    def if_read(self, m):
        with self.with_guard():
            m.d.comb += self.fifo.r_en.eq(1)
        return self.fifo.r_rdy, {'data': self.fifo.r_data}

    @interface_method(lambda self: ([('data', self.width)], []))
    def if_write(self, m, data):
        with self.with_guard():
            m.d.comb += self.fifo.w_en.eq(1)
        m.d.comb += self.fifo.w_data.eq(data)
        return self.fifo.w_rdy, {}
   
    def elaborate(self, platform):
        m = Module()

        m.submodules.fifo = self.fifo

        self.finalize(m)
        return m

class CopyTrans(Elaboratable):
    def __init__(self, src, dst):
        self.src = src
        self.dst = dst

    def elaborate(self, platform):
        m = Module()

        with Transaction(m):
            data = self.src.if_read()
            self.dst.if_put(data=data)

        return m

class CatTrans(Elaboratable):
    def __init__(self, src1, src2, dst):
        self.src1 = src1
        self.src2 = src2
        self.dst = dst

    def elaborate(self, platform):
        m = Module()

        with Transaction(m):
            data1 = self.src1.if_get()
            data2 = self.src2.if_get()

            self.dst.if_write(data=Cat(data1.data, data2.data))

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
