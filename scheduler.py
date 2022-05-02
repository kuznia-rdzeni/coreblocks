from amaranth import *
from transactions import Method, Transaction, TransactionModule, TransactionContext
from transactions.lib import FIFO, ConnectTrans, AdapterTrans
import random
import queue

class RegAllocation(Elaboratable):
    def __init__(self, get_free_reg : Method, phys_regs_bits=6):
        self.get_free_reg = get_free_reg
        self.phys_regs_bits = phys_regs_bits
        self.input_layout = [
            ('rlog_1', 5),
            ('rlog_2', 5),
            ('rlog_out', 5)
        ]
        self.output_layout = [
            ('rlog_1', 5),
            ('rlog_2', 5),
            ('rlog_out', 5),
            ('rphys_out', phys_regs_bits)
        ]
        self.if_put = Method(i=self.input_layout)
        self.if_get = Method(o=self.output_layout)

    def elaborate(self, platform):
        m = Module()

        instr = Record(self.input_layout)
        free_reg = Signal(self.phys_regs_bits)
        out_rec = Record(self.output_layout)

        with m.FSM():
            with m.State('wait_input'):
                with self.if_put.when_called(m) as arg:
                    m.d.sync += instr.eq(arg)
                    with m.If(arg.rlog_out != 0):
                        m.next = 'get_free_reg'
                    with m.Else():
                        m.next = 'wait_output'

            with m.State('get_free_reg'):
                with Transaction().when_granted(m):
                    reg_id = self.get_free_reg()
                    m.d.sync += free_reg.eq(reg_id)
                    m.next = 'wait_output'

            with m.State('wait_output'):
                with self.if_get.when_called(m, ret=out_rec):
                    m.d.comb += out_rec.rlog_1.eq(instr.rlog_1)
                    m.d.comb += out_rec.rlog_2.eq(instr.rlog_2)
                    m.d.comb += out_rec.rlog_out.eq(instr.rlog_out)
                    m.d.comb += out_rec.rphys_out.eq(Mux(instr.rlog_out != 0, free_reg, 0))
                    m.next = 'wait_input'

        return m

class Renaming(Elaboratable):
    def __init__(self, f_rat, phys_regs_bits=6):
        self.input_layout = [
            ('rlog_1', 5),
            ('rlog_2', 5),
            ('rlog_out', 5),
            ('rphys_out', phys_regs_bits)
        ]
        self.output_layout = [
            ('rphys_1', phys_regs_bits),
            ('rphys_2', phys_regs_bits),
            ('rlog_out', 5),
            ('rphys_out', phys_regs_bits)
        ]
        self.phys_regs_bits = phys_regs_bits
        self.if_put = Method(i=self.input_layout)
        self.if_get = Method(o=self.output_layout)
        self.f_rat = f_rat

    def elaborate(self, platform):
        m = Module()

        data_in = Record(self.input_layout)
        data_out = Record(self.output_layout)
        rphys_1 = Signal(self.phys_regs_bits)
        rphys_2 = Signal(self.phys_regs_bits)

        with m.FSM():
            with m.State('wait_input'):
                with self.if_put.when_called(m) as arg:
                    m.d.sync += data_in.eq(arg)
                    m.next = 'rename_regs'

            with m.State('rename_regs'):
                with Transaction().when_granted(m):
                    renamed = self.f_rat.if_rename(arg=data_in)
                    m.d.sync += rphys_1.eq(renamed.rphys_1)
                    m.d.sync += rphys_2.eq(renamed.rphys_2)
                    m.next = 'wait_output'

            with m.State('wait_output'):
                with self.if_get.when_called(m, ret=data_out) as arg:
                    m.d.comb += data_out.rlog_out.eq(data_in.rlog_out)
                    m.d.comb += data_out.rphys_out.eq(data_in.rphys_out)
                    m.d.comb += data_out.rphys_1.eq(rphys_1)
                    m.d.comb += data_out.rphys_2.eq(rphys_2)
                    m.next = 'wait_input'

        return m

class RAT(Elaboratable):
    def __init__(self, phys_regs_bits=6):
        self.input_layout = [
            ('rlog_1', 5),
            ('rlog_2', 5),
            ('rlog_out', 5),
            ('rphys_out', phys_regs_bits)
        ]
        self.output_layout = [
            ('rphys_1', phys_regs_bits),
            ('rphys_2', phys_regs_bits)
        ]
        
        self.entries = Array((Signal(phys_regs_bits, reset=i) for i in range(32)))
        self.phys_regs_bits = phys_regs_bits

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

        instr_layout = [
            ('rlog_1', 5),
            ('rlog_2', 5),
            ('rlog_out', 5)
        ]
        
        instr_width = Signal.like(Record(instr_layout)).width

        with tm.transactionContext():
            m.submodules.instr_fifo = instr_fifo = FIFO(instr_width, 16)
            m.submodules.free_rf_fifo = free_rf_fifo = FIFO(phys_regs_bits, 2**phys_regs_bits)

            m.submodules.reg_alloc = reg_alloc = RegAllocation(free_rf_fifo.read, phys_regs_bits)
            m.submodules.rat = rat = RAT(phys_regs_bits)
            m.submodules.renaming = renaming = Renaming(rat, phys_regs_bits)
            
            m.submodules += ConnectTrans(instr_fifo.read, reg_alloc.if_put)
            m.submodules += ConnectTrans(reg_alloc.if_get, renaming.if_put)

            # mocked input and output
            m.submodules.output = out = AdapterTrans(renaming.if_get, o=renaming.output_layout) 
            m.submodules.instr_input = instr_inp = AdapterTrans(instr_fifo.write, i=instr_layout)
            m.submodules.free_rf_inp = free_rf_inp = AdapterTrans(free_rf_fifo.write, i=[('data', phys_regs_bits)])

        return tm

# Testbench code

expected_rename = queue.Queue()
expected_phys_reg = queue.Queue()
current_RAT = [x for x in range(0, 32)]
recycled_regs = queue.Queue()

def check_renamed(rphys_1, rphys_2, rlog_out, rphys_out):
    assert((yield out.data_out.rphys_1) == rphys_1)
    assert((yield out.data_out.rphys_2) == rphys_2)
    assert((yield out.data_out.rlog_out) == rlog_out)
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
    phys_regs_bits = 6
    m = RenameTestCircuit()
    sim = Simulator(m)
    sim.add_clock(1e-6)
    sim.add_sync_process(bench_output)
    sim.add_sync_process(bench_instr_input)
    sim.add_sync_process(bench_free_rf_input)

    for i in range(1, 2**phys_regs_bits):
        recycle_phys_reg(i)

    with sim.write_vcd("dump.vcd"):
        sim.run()
        print("Test OK")
    with open("result.v", "w") as f:
        f.write(verilog.convert(m, ports=[]))