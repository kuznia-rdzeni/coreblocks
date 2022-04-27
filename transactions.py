
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

        grant_reg = Signal.like(self.grant)

        with m.Switch(grant_reg):
            for i in range(self.count):
                with m.Case("-"*(self.count-i-1) + "1" + "-"*i):
                    for j in itertools.chain(reversed(range(i)), reversed(range(i+1, self.count))):
                        with m.If(self.requests[j]):
                            m.d.comb += self.grant.eq(1 << j)
            with m.Case():
                m.d.comb += self.grant.eq(0)

        m.d.comb += self.valid.eq(self.requests.any())

        m.d.sync += grant_reg.eq(self.grant)

        return m

def _graph_ccs(gr):
    ccs = []
    cc = set()
    visited = set()

    for v in gr.keys():
        q = [v]
        while q:
            w = q.pop()
            if w in visited: continue
            visited.add(w)
            cc.add(w)
            q.extend(gr[w])
        if cc:
            ccs.append(cc)
            cc = set()

    return ccs

class TransactionManager(Elaboratable):
    def __init__(self):
        self.transactions = {}
        self.methods = {}

    def use_method(self, transaction : 'Transaction', method : 'Method', arg=C(0, 0)):
        assert transaction.manager is self and method.manager is self
        if not transaction in self.transactions:
            self.transactions[transaction] = []
        if not method in self.methods:
            self.methods[method] = []
        self.transactions[transaction].append(method)
        self.methods[method].append((transaction, arg))
        return method.data_out

    def _conflict_graph(self):
        gr = {}

        for transaction in self.transactions.keys():
            gr[transaction] = set()

        for transaction, methods in self.transactions.items():
            for method in methods:
                for transaction2, _ in self.methods[method]:
                    if transaction is not transaction2:
                        gr[transaction].add(transaction2)
                        gr[transaction2].add(transaction)

        return gr

    def elaborate(self, platform):
        m = Module()

        gr = self._conflict_graph()

        for cc in _graph_ccs(gr):
            sched = Scheduler(len(cc))
            m.submodules += sched
            for k, transaction in enumerate(cc):
                methods = self.transactions[transaction]
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

                with m.If(transaction.grant):
                    m.d.comb += method.data_in.eq(tdata)
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
                self.module._named_submodules[name] = Fragment.get(self.module._named_submodules[name], platform)
            for idx in range(len(self.module._anon_submodules)):
                self.module._anon_submodules[idx] = Fragment.get(self.module._anon_submodules[idx], platform)

        self.module.submodules += self.transactionManager

        return self.module

class Transaction:
    current = None

    def __init__(self, *, request=C(1), manager : TransactionManager = None):
        if manager is None:
            manager = TransactionContext.get()
        self.request = request
        self.grant = Signal()
        self.manager = manager

    def __enter__(self):
        if self.__class__.current is not None:
            raise RuntimeError("Transaction inside transaction")
        self.__class__.current = self
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        self.__class__.current = None

    @classmethod
    def get(cls):
        if cls.current is None:
            raise RuntimeError("No current transaction")
        return cls.current

class Method:
    def __init__(self, *, i=0, o=0, manager : TransactionManager = None):
        if manager is None:
            manager = TransactionContext.get()
        self.ready = Signal()
        self.run = Signal()
        self.manager = manager
        if isinstance(i, int):
            i = [('data', i)]
        self.data_in = Record(i)
        if isinstance(o, int):
            o = [('data', o)]
        self.data_out = Record(o)

    @contextmanager
    def when_called(self, m : Module, ready=C(1), ret=C(0, 0)):
        m.d.comb += self.ready.eq(ready)
        m.d.comb += self.data_out.eq(ret)
        with m.If(self.run):
            yield self.data_in

    def __call__(self, arg=C(0, 0)):
        trans = Transaction.get()
        return self.manager.use_method(trans, self, arg)

# FIFOs

import amaranth.lib.fifo

class OpFIFO(Elaboratable):
    def __init__(self, width, depth):
        self.width = width
        self.depth = depth

        self.read = Method(o=width)
        self.write = Method(i=width)
   
    def elaborate(self, platform):
        m = Module()

        m.submodules.fifo = fifo = amaranth.lib.fifo.SyncFIFO(width=self.width, depth=self.depth)

        with self.write.when_called(m, fifo.w_rdy) as arg:
            m.d.comb += fifo.w_en.eq(1)
            m.d.comb += fifo.w_data.eq(arg)

        with self.read.when_called(m, fifo.r_rdy, fifo.r_data):
            m.d.comb += fifo.r_en.eq(1)

        return m

# "Clicked" input

class OpIn(Elaboratable):
    def __init__(self, width=1):
        self.get = Method(o=width)
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
        get_ready = Signal()
        get_data = Signal()

        with self.get.when_called(m, get_ready, get_data):
            m.d.sync += get_ready.eq(0)

        with m.If(~btn2 & btn1):
            m.d.sync += get_ready.eq(1)
            m.d.sync += get_data.eq(dat1)

        return m

# "Clicked" output

class OpOut(Elaboratable):
    def __init__(self, width=1):
        self.put = Method(i=width)
        self.btn = Signal()
        self.dat = Signal(width)

    def elaborate(self, platform):
        m = Module()

        btn1 = Signal()
        btn2 = Signal()
        m.d.sync += btn1.eq(self.btn)
        m.d.sync += btn2.eq(btn1)
        
        with self.put.when_called(m, ~btn2 & btn1) as arg:
            m.d.sync += self.dat.eq(arg)

        return m

# Example transactions

class CopyTrans(Elaboratable):
    def __init__(self, src : Method, dst : Method):
        self.src = src
        self.dst = dst

    def elaborate(self, platform):
        m = Module()
        
        with Transaction() as trans:
            sdata = self.src()
            ddata = Record.like(sdata)
            self.dst(ddata)

            m.d.comb += ddata.eq(sdata)

        return m

class CatTrans(Elaboratable):
    def __init__(self, src1 : Method, src2 : Method, dst : Method):
        self.src1 = src1
        self.src2 = src2
        self.dst = dst
    
    def elaborate(self, platform):
        m = Module()
        
        with Transaction() as trans:
            sdata1 = self.src1()
            sdata2 = self.src2()
            ddata = Record.like(self.dst.data_in)
            self.dst(ddata)

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
            m.submodules.cti = CatTrans(in1.get, in2.get, fifo.write)
            m.submodules.cto = CopyTrans(fifo.read, out.put)
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




