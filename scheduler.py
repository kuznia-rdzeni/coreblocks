from amaranth import *
from transactions import Method, Transaction, TransactionModule, TransactionContext
from transactions.lib import FIFO, ConnectTrans, AdapterTrans
import random
import queue

def layout_width(layout):
    return Signal.like(Record(layout)).width

RPHYS_WIDTH = 6

class RegAlloc(Elaboratable):

    input_layout = [
        ('rlog_1', 5),
        ('rlog_2', 5),
        ('rlog_out', 5)
    ]

    output_layout = [
        ('rlog_1', 5),
        ('rlog_2', 5),
        ('rlog_out', 5),
        ('rphys_out', RPHYS_WIDTH)
    ]

    def __init__(self, dequeue : Method, get_rf_slot : Method,
                 enqueue : Method):
        self.get_rf_slot = get_rf_slot
        self.dequeue = dequeue
        self.get_rf_slot = get_rf_slot
        self.enqueue = enqueue

    def elaborate(self, platform):
        m = Module()

        with Transaction().when_granted(m):
            instr_data = self.dequeue(m)
            instr = Record(self.input_layout)
            m.d.comb += instr.eq(instr_data)
            rf_slot = Signal(RPHYS_WIDTH)
            with m.If(instr.rlog_out != 0):
                m.d.comb += rf_slot.eq(self.get_rf_slot(m))
            output = Record(self.output_layout)
            m.d.comb += [
                output.rlog_1.eq(instr.rlog_1),
                output.rlog_2.eq(instr.rlog_2),
                output.rlog_out.eq(instr.rlog_out),
                output.rphys_out.eq(rf_slot),
            ]
            self.enqueue(m, output)

        return m


class Renaming(Elaboratable):

    input_layout = [
        ('rlog_1', 5),
        ('rlog_2', 5),
        ('rlog_out', 5),
        ('rphys_out', RPHYS_WIDTH)
    ]

    output_layout = [
        ('rphys_1', RPHYS_WIDTH),
        ('rphys_2', RPHYS_WIDTH),
        ('rlog_out', 5),
        ('rphys_out', RPHYS_WIDTH)
    ]

    def __init__(self, dequeue : Method, rename : Method,
                 enqueue : Method):
        self.dequeue = dequeue
        self.rename = rename
        self.enqueue = enqueue

    def elaborate(self, platform):
        m = Module()

        with Transaction().when_granted(m):
            instr_data = self.dequeue(m)
            instr = Record(self.input_layout)
            m.d.comb += instr.eq(instr_data)
            renamed = self.rename(m, instr)
            output = Record(self.output_layout)
            m.d.comb += [
                output.rphys_1.eq(renamed.rphys_1),
                output.rphys_2.eq(renamed.rphys_2),
                output.rlog_out.eq(instr.rlog_out),
                output.rphys_out.eq(instr.rphys_out),
            ]
            self.enqueue(m, output)

        return m

class RAT(Elaboratable):

    input_layout = [
        ('rlog_1', 5),
        ('rlog_2', 5),
        ('rlog_out', 5),
        ('rphys_out', RPHYS_WIDTH)
    ]

    output_layout = [
        ('rphys_1', RPHYS_WIDTH),
        ('rphys_2', RPHYS_WIDTH)
    ]

    def __init__(self):
        self.entries = Array((Signal(RPHYS_WIDTH, reset=i) for i in range(32)))
        self.if_rename = Method(i=self.input_layout, o=self.output_layout)

    def elaborate(self, platform):
        m = Module()
        renamed = Record(self.output_layout)

        with self.if_rename.when_called(m, ret=renamed) as arg:
            m.d.comb += renamed.rphys_1.eq(self.entries[arg.rlog_1])
            m.d.comb += renamed.rphys_2.eq(self.entries[arg.rlog_2])
            m.d.sync += self.entries[arg.rlog_out].eq(arg.rphys_out)
        return m

class RenameTestCircuit(Elaboratable):
    def elaborate(self, platform):
        global out, instr_inp, free_rf_inp
        m = Module()
        tm = TransactionModule(m)

        with tm.transactionContext():
            m.submodules.instr_fifo = instr_fifo = \
                FIFO(layout_width(RegAlloc.input_layout), 16)
            m.submodules.free_rf_fifo = free_rf_fifo = \
                FIFO(RPHYS_WIDTH, 2**RPHYS_WIDTH)

            m.submodules.buf1 = buf1 = \
                FIFO(layout_width(RegAlloc.output_layout), 2)
            m.submodules.reg_alloc = reg_alloc = \
                RegAlloc(instr_fifo.read, free_rf_fifo.read,
                              buf1.write)
            m.submodules.rat = rat = RAT()
            m.submodules.buf2 = buf2 = FIFO(layout_width(Renaming.output_layout), 2)
            m.submodules.renaming = renaming = \
                Renaming(buf1.read, rat.if_rename, buf2.write)

            m.submodules.instr_input = instr_inp = AdapterTrans(instr_fifo.write, i=RegAlloc.input_layout)
            m.submodules.free_rf_inp = free_rf_inp = AdapterTrans(free_rf_fifo.write, i=[('rphys_out', RPHYS_WIDTH)])
            m.submodules.output = out = AdapterTrans(buf2.read, o=Renaming.output_layout)

        return tm

# Testbench code

expected_rename = queue.Queue()
expected_phys_reg = queue.Queue()
current_RAT = [x for x in range(0, 32)]
recycled_regs = queue.Queue()

def check_renamed(rphys_1, rphys_2, rlog_out, rphys_out):
    assert((yield out.data_out.rphys_1) == rphys_1)
    assert((yield out.data_out.rphys_2) == rphys_2)
    rlog_out_2 = yield out.data_out.rlog_out
    assert(rlog_out_2 == rlog_out)
    assert((yield out.data_out.rphys_out) == rphys_out)

def put_instr(rlog_1, rlog_2, rlog_out):
    yield (instr_inp.data_in.rlog_1.eq(rlog_1))
    yield (instr_inp.data_in.rlog_2.eq(rlog_2))
    yield (instr_inp.data_in.rlog_out.eq(rlog_out))
    yield
    while (yield instr_inp.done) != 1:
        yield

def recycle_phys_reg(reg_id):
    recycled_regs.put(reg_id)
    expected_phys_reg.put(reg_id)

def bench_output():
    while True:
        try:
            item = expected_rename.get_nowait()
            if item is None:
                yield out.en.eq(0)
                return
            yield out.en.eq(1)
            yield
            while (yield out.done) != 1:
                yield
            yield from check_renamed(**item)
            yield out.en.eq(0)
            # recycle physical register number
            if item['rphys_out'] != 0:
                recycle_phys_reg(item['rphys_out'])
        except queue.Empty:
            yield

def bench_instr_input():
    yield (instr_inp.en.eq(1))
    for i in range(500):
        rlog_1 = random.randint(0, 31)
        rlog_2 = random.randint(0, 31)
        rlog_out = random.randint(0, 31)
        rphys_1 = current_RAT[rlog_1]
        rphys_2 = current_RAT[rlog_2]
        rphys_out = expected_phys_reg.get() if rlog_out != 0 else 0

        expected_rename.put({'rphys_1': rphys_1, 'rphys_2': rphys_2, 'rlog_out': rlog_out, 'rphys_out': rphys_out})
        current_RAT[rlog_out] = rphys_out

        yield from put_instr(rlog_1, rlog_2, rlog_out)

    yield (instr_inp.en.eq(0))
    expected_rename.put(None)
    recycled_regs.put(None)

def bench_free_rf_input():
    while True:
        try:
            reg = recycled_regs.get_nowait()
            if reg is None:
                yield free_rf_inp.en.eq(0)
                return
            yield free_rf_inp.en.eq(1)
            yield free_rf_inp.data_in.eq(reg)
            yield
            while (yield free_rf_inp.done) != 1:
                yield
            yield free_rf_inp.en.eq(0)
        except queue.Empty:
            yield

if __name__ == "__main__":
    from amaranth.back import verilog
    from amaranth.sim import Simulator, Settle

    random.seed(42)
    m = RenameTestCircuit()
    sim = Simulator(m)
    sim.add_clock(1e-6)
    sim.add_sync_process(bench_output)
    sim.add_sync_process(bench_instr_input)
    sim.add_sync_process(bench_free_rf_input)

    for i in range(1, 2**RPHYS_WIDTH):
        recycle_phys_reg(i)

    with sim.write_vcd("dump.vcd"):
        sim.run()
        print("Test OK")
    with open("result.v", "w") as f:
        f.write(verilog.convert(m, ports=[]))
