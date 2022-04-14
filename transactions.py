
import itertools
from contextlib import contextmanager
from amaranth import *

class Scheduler(Elaboratable):
    def __init__(self, count: int):
        if not isinstance(count, int) or count < 0:
            raise ValueError("Count must be a non-negative integer, not {!r}"
                             .format(count))
        self.count = count

        self.requests = Signal(count)
        self.grant    = Signal(count, reset=1)
        self.valid    = Signal()

    def elaborate(self, platform):
        m = Module()

        for i in range(self.count):
            with m.If(self.grant):
                for j in itertools.chain(reversed(range(i)), reversed(range(i+1, self.count))):
                    with m.If(self.requests[j]):
                        m.d.sync += self.grant.eq(1 << j)

        m.d.sync += self.valid.eq(self.requests.any())

        return m

class TransactionManager(Elaboratable):
    def __init__(self):
        self.transactions = {}
        self.methods = {}

    def use_method(self, transaction : 'Transaction', method : 'Method'):
        if method.consumer:
            data = Record.like(method.data)
        else:
            data = None
        self.transactions[transaction].append(method)
        self.methods[method].append((transaction, data))
        if method.consumer:
            return data
        else:
            return method.data

    def elaborate(self, platform):
        m = Module()

        m.submodules.sched = sched = Scheduler(len(self.transactions))

        for k, (transaction, methods) in enumerate(self.transactions.items()):
            ready = Signal(len(methods))
            for n, method in enumerate(methods):
                m.d.comb += ready[n].eq(method.ready)
            runnable = ready.all()
            m.d.comb += sched.requests[k].eq(transaction.request & runnable)
            m.d.comb += transaction.grant.eq(sched.grant[k] & sched.valid)

        for method, transactions in self.methods.items():
            granted = Signal(len(transactions))
            for n, (transaction, tdata) in enumerate(transactions):
                m.d.comb += granted[n].eq(transaction.grant)

                if method.consumer:
                    with m.If(transaction.grant):
                        m.d.comb += method.data.eq(tdata)
            runnable = granted.any()
            m.d.comb += method.run.eq(runnable)

        return m

class TransactionContext:
    stack = []

    def __init__(self, manager : TransactionManager):
        self.manager = manager

    def __enter__(self):
        self.stack.append(self.manager)
        return self
    
    def __exit__(self, exc_type, exc_value, exc_tb):
        top = self.stack.pop()
        assert self.manager is top

    @classmethod
    def get(cls):
        if not cls.stack:
            raise RuntimeError("TransactionContext stack is empty")
        return cls.stack[-1]

class TransactionModule(Elaboratable):
    def __init__(self, module):
        Module.__init__(self)
        self.transactionManager = TransactionManager()
        self.module = module

    def transactionContext(self):
        return TransactionContext(self.transactionManager)

    def elaborate(self, platform):
        with self.transactionContext():
            for name in self.module._named_submodules:
                self.module._named_submodules[name] = amaranth.Fragment.get(self.module._named_submodules[name], platform)
            for idx in range(len(self.module._anon_submodules)):
                self.module._anon_submodules[idx] = amaranth.Fragment.get(self.module._anon_submodules[idx], platform)

        self.module.submodules += self.transactionManager

        return self.module

class Transaction:
    def __init__(self, *, manager : TransactionManager = None):
        if manager is None:
            manager = TransactionContext.get()
        manager.transactions[self] = []
        self.request = Signal()
        self.grant = Signal()
        self.manager = manager

    def use_method(self, method):
        return self.manager.use_method(self, method)

class Method:
    def __init__(self, layout, *, consumer : bool = False, manager : TransactionManager = None):
        if manager is None:
            manager = TransactionContext.get()
        manager.methods[self] = []
        self.ready = Signal()
        self.run = Signal()
        self.simple = isinstance(layout, int)
        if self.simple:
            layout = [('data', layout)]
        self.data = Record(layout)
        self.consumer = consumer

# FIFOs

import amaranth.lib.fifo

class OpFIFO(Elaboratable):
    def __init__(self, width, depth):
        self.width = width
        self.depth = depth

        self.read_op = Method(width)
        self.write_op = Method(width, consumer=True)
   
    def elaborate(self, platform):
        m = Module()

        m.submodules.fifo = fifo = amaranth.lib.fifo.SyncFIFO(width=self.width, depth=self.depth)

        m.d.comb += self.read_op.ready.eq(fifo.r_rdy)
        m.d.comb += self.write_op.ready.eq(fifo.w_rdy)
        m.d.comb += fifo.r_en.eq(self.read_op.run)
        m.d.comb += fifo.w_en.eq(self.write_op.run)
        m.d.comb += self.read_op.data.eq(fifo.r_data)
        m.d.comb += fifo.w_data.eq(self.write_op.data)

        return m

# "Clicked" input

class OpIn(Elaboratable):
    def __init__(self, width=1):
        self.op = Method(width)
        self.btn = Signal()
        self.dat = Signal(width)

    def elaborate(self, platform):
        m = Module()

        btn1 = Signal()
        btn2 = Signal()
        dat1 = Signal.like(self.dat)
        m.d.sync += btn1.eq(self.btn)
        m.d.sync += btn2.eq(btn1)
        m.d.sync += dat1.eq(self.dat)

        with m.If(self.op.run):
            m.d.sync += self.op.ready.eq(0)
        with m.If(~btn2 & btn1):
            m.d.sync += self.op.ready.eq(1)
            m.d.sync += self.op.data.eq(dat1)

        return m

# "Clicked" output

class OpOut(Elaboratable):
    def __init__(self, width=1):
        self.op = Method(width, consumer=True)
        self.btn = Signal()
        self.dat = Signal(width)

    def elaborate(self, platform):
        m = Module()

        btn1 = Signal()
        btn2 = Signal()
        m.d.sync += btn1.eq(self.btn)
        m.d.sync += btn2.eq(btn1)
        
        m.d.comb += self.op.ready.eq(~btn2 & btn1)
        with m.If(self.op.run):
            m.d.sync += self.dat.eq(self.op.data)

        return m

# Example transactions

class CopyTrans(Elaboratable):
    def __init__(self, src : Method, dst : Method):
        self.src = src
        self.dst = dst

    def elaborate(self, platform):
        m = Module()
        
        trans = Transaction()
        sdata = trans.use_method(self.src)
        ddata = trans.use_method(self.dst)

        m.d.comb += trans.request.eq(1)
        m.d.comb += ddata.eq(sdata)

        return m

class CatTrans(Elaboratable):
    def __init__(self, src1 : Method, src2 : Method, dst : Method):
        self.src1 = src1
        self.src2 = src2
        self.dst = dst
    
    def elaborate(self, platform):
        m = Module()
        
        trans = Transaction()
        sdata1 = trans.use_method(self.src1)
        sdata2 = trans.use_method(self.src2)
        ddata = trans.use_method(self.dst)

        m.d.comb += trans.request.eq(1)
        m.d.comb += ddata.eq(Cat(sdata1, sdata2))

        return m

# Example

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
            m.submodules.fifo = fifo = OpFIFO(2, 16)
            m.submodules.in1 = in1 = OpIn()
            m.submodules.in2 = in2 = OpIn()
            m.submodules.out = out = OpOut(2)
            m.submodules.cti = CatTrans(in1.op, in2.op, fifo.write_op)
            m.submodules.cto = CopyTrans(fifo.read_op, out.op)
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




