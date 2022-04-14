
import itertools
from amaranth import *

class Scheduler(Elaboratable):
    def __init__(self, count):
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
        self.operations = {}

    def add_transaction(self):
        transaction = Transaction(self)
        self.transactions[transaction] = []
        return transaction

    def add_operation(self, width=0, *, consumer=False):
        operation = Operation(width, consumer)
        self.operations[operation] = []
        return operation

    def use_operation(self, transaction, operation):
        if operation.consumer:
            data = Signal(operation.data.width)
        else:
            data = None
        self.transactions[transaction].append(operation)
        self.operations[operation].append((transaction, data))
        if operation.consumer:
            return data
        else:
            return operation.data

    def elaborate(self, platform):
        m = Module()

        m.submodules.sched = sched = Scheduler(len(self.transactions))

        for k, (transaction, operations) in enumerate(self.transactions.items()):
            ready = Signal(len(operations))
            for n, operation in enumerate(operations):
                m.d.comb += ready[n].eq(operation.ready)
            runnable = ready.all()
            m.d.comb += sched.requests[k].eq(transaction.request & runnable)
            m.d.comb += transaction.grant.eq(sched.grant[k] & sched.valid)

        for operation, transactions in self.operations.items():
            granted = Signal(len(transactions))
            for n, (transaction, tdata) in enumerate(transactions):
                m.d.comb += granted[n].eq(transaction.grant)

                if operation.consumer:
                    with m.If(transaction.grant):
                        m.d.comb += operation.data.eq(tdata)
            runnable = granted.any()
            m.d.comb += operation.run.eq(runnable)

        return m

class Transaction:
    def __init__(self, manager):
        self.request = Signal()
        self.grant = Signal()
        self.manager = manager

    def use_operation(self, operation):
        return self.manager.use_operation(self, operation)

class Operation:
    def __init__(self, width, consumer):
        self.ready = Signal()
        self.run = Signal()
        self.data = Signal(width)
        self.consumer = consumer

# FIFOs

import amaranth.lib.fifo

class OpFIFO(Elaboratable):
    def __init__(self, manager, width, depth):
        self.width = width
        self.depth = depth

        self.read_op = manager.add_operation(width)
        self.write_op = manager.add_operation(width, consumer=True)
   
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
    def __init__(self, manager, width=1):
        self.op = manager.add_operation(width)
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
    def __init__(self, manager, width=1):
        self.op = manager.add_operation(width, consumer=True)
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
    def __init__(self, manager, src, dst):
        self.src = src
        self.dst = dst
        self.trans = manager.add_transaction()
        self.sdata = self.trans.use_operation(src)
        self.ddata = self.trans.use_operation(dst)

    def elaborate(self, platform):
        m = Module()

        m.d.comb += self.trans.request.eq(1)
        m.d.comb += self.ddata.eq(self.sdata)

        return m

class CatTrans(Elaboratable):
    def __init__(self, manager, src1, src2, dst):
        self.src1 = src1
        self.src2 = src2
        self.trans = manager.add_transaction()
        self.sdata1 = self.trans.use_operation(src1)
        self.sdata2 = self.trans.use_operation(src2)
        self.ddata = self.trans.use_operation(dst)
    
    def elaborate(self, platform):
        m = Module()

        m.d.comb += self.trans.request.eq(1)
        m.d.comb += self.ddata.eq(Cat(self.sdata1, self.sdata2))

        return m

# Example

class SimpleCircuit(Elaboratable):
    def __init__(self):
        manager = TransactionManager()
        fifo = OpFIFO(manager, 2, 16)
        in1 = OpIn(manager)
        in2 = OpIn(manager)
        out = OpOut(manager, 2)
        self.submodules = {
            'manager': manager,
            'fifo': fifo,
            'in1': in1, 'in2': in2, 'out': out,
            'cti': CatTrans(manager, in1.op, in2.op, fifo.write_op),
            'cto': CopyTrans(manager, fifo.read_op, out.op)
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




