from amaranth import *
from transactions import Method, Transaction, TransactionModule, TransactionContext
from transactions.lib import FIFO, ConnectTrans, AdapterTrans

class RegAllocation(Elaboratable):
    def __init__(self, *, get_instr : Method, push_instr : Method, get_free_reg : Method, phys_regs_bits=6):
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
        self.get_instr = get_instr
        self.push_instr = push_instr

    def elaborate(self, platform):
        m = Module()

        free_reg = Signal(self.phys_regs_bits)
        data_out = Record(self.output_layout)

        with Transaction().when_granted(m):
            instr = self.get_instr(m)
            with m.If(instr.rlog_out != 0):
                reg_id = self.get_free_reg(m)
                m.d.comb += free_reg.eq(reg_id)

            m.d.comb += data_out.rlog_1.eq(instr.rlog_1)
            m.d.comb += data_out.rlog_2.eq(instr.rlog_2)
            m.d.comb += data_out.rlog_out.eq(instr.rlog_out)
            m.d.comb += data_out.rphys_out.eq(free_reg)
            self.push_instr(m, data_out)

        return m

class Renaming(Elaboratable):
    def __init__(self, *, get_instr : Method, push_instr : Method, rename : Method, phys_regs_bits=6):
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
        self.get_instr = get_instr
        self.push_instr = push_instr
        self.rename = rename

    def elaborate(self, platform):
        m = Module()

        data_in = Record(self.input_layout)
        data_out = Record(self.output_layout)
        rphys_1 = Signal(self.phys_regs_bits)
        rphys_2 = Signal(self.phys_regs_bits)

        with Transaction().when_granted(m):
            instr = self.get_instr(m)
            renamed_regs = self.rename(m, instr)

            m.d.comb += data_out.rlog_out.eq(instr.rlog_out)
            m.d.comb += data_out.rphys_out.eq(instr.rphys_out)
            m.d.comb += data_out.rphys_1.eq(renamed_regs.rphys_1)
            m.d.comb += data_out.rphys_2.eq(renamed_regs.rphys_2)
            self.push_instr(m, data_out)

        return m

class RAT(Elaboratable):
    def __init__(self, *, phys_regs_bits=6):
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
        m = Module()
        tm = TransactionModule(m)

        instr_record = Record([
            ('rlog_1', 5),
            ('rlog_2', 5),
            ('rlog_out', 5)
        ])

        with tm.transactionContext():
            m.submodules.instr_fifo = instr_fifo = FIFO(instr_record.layout, 16)
            m.submodules.free_rf_fifo = free_rf_fifo = FIFO(phys_regs_bits, 2**phys_regs_bits)
            
            m.submodules.reg_alloc = reg_alloc = RegAllocation(get_instr=instr_fifo.read, push_instr=None, get_free_reg=free_rf_fifo.read, phys_regs_bits=phys_regs_bits)
            m.submodules.alloc_rename_buf = alloc_rename_buf = FIFO(reg_alloc.output_layout, 2)
            reg_alloc.push_instr = alloc_rename_buf.write
            m.submodules.rat = rat = RAT(phys_regs_bits=phys_regs_bits)
            m.submodules.renaming = renaming = Renaming(get_instr=alloc_rename_buf.read, push_instr=None, rename=rat.if_rename, phys_regs_bits=phys_regs_bits)
            m.submodules.rename_out_buf = rename_out_buf = FIFO(renaming.output_layout, 2)
            renaming.push_instr = rename_out_buf.write
            # mocked input and output
            m.submodules.output = self.out = AdapterTrans(rename_out_buf.read, o=renaming.output_layout)
            m.submodules.instr_input = self.instr_inp = AdapterTrans(instr_fifo.write, i=instr_record.layout)
            m.submodules.free_rf_inp = self.free_rf_inp = AdapterTrans(free_rf_fifo.write, i=[('data', phys_regs_bits)])

        return tm

if __name__ == "__main__":
    import random
    import queue
    from amaranth.back import verilog
    from amaranth.sim import Simulator, Settle

    # Testbench code
    random.seed(42)
    phys_regs_bits = 6

    expected_rename = queue.Queue()
    expected_phys_reg = queue.Queue()
    current_RAT = [x for x in range(0, 32)]
    recycled_regs = queue.Queue()

    m = RenameTestCircuit()

    def check_renamed(rphys_1, rphys_2, rlog_out, rphys_out):
        assert((yield m.out.data_out.rphys_1) == rphys_1)
        assert((yield m.out.data_out.rphys_2) == rphys_2)
        assert((yield m.out.data_out.rlog_out) == rlog_out)
        assert((yield m.out.data_out.rphys_out) == rphys_out)

    def put_instr(rlog_1, rlog_2, rlog_out):
        yield (m.instr_inp.data_in.rlog_1.eq(rlog_1))
        yield (m.instr_inp.data_in.rlog_2.eq(rlog_2))
        yield (m.instr_inp.data_in.rlog_out.eq(rlog_out))
        yield
        while (yield m.instr_inp.done) != 1:
            yield

    def recycle_phys_reg(reg_id):
        recycled_regs.put(reg_id)
        expected_phys_reg.put(reg_id)

    def bench_output():
        while True:
            try:
                item = expected_rename.get_nowait()
                if item is None:
                    yield m.out.en.eq(0)
                    return
                yield m.out.en.eq(1)
                yield
                while (yield m.out.done) != 1:
                    yield
                yield from check_renamed(**item)
                yield m.out.en.eq(0)
                # recycle physical register number
                if item['rphys_out'] != 0:
                    recycle_phys_reg(item['rphys_out'])
            except queue.Empty:
                yield

    def bench_instr_input():
        yield (m.instr_inp.en.eq(1))
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

        yield (m.instr_inp.en.eq(0))
        expected_rename.put(None)
        recycled_regs.put(None)
        
    def bench_free_rf_input():
        while True:
            try:
                reg = recycled_regs.get_nowait()
                if reg is None:
                    yield m.free_rf_inp.en.eq(0)
                    return
                yield m.free_rf_inp.en.eq(1)
                yield m.free_rf_inp.data_in.eq(reg)
                yield
                while (yield m.free_rf_inp.done) != 1:
                    yield
                yield m.free_rf_inp.en.eq(0)
            except queue.Empty:
                yield

    for i in range(1, 2**phys_regs_bits):
        recycle_phys_reg(i)

    sim = Simulator(m)
    sim.add_clock(1e-6)
    sim.add_sync_process(bench_output)
    sim.add_sync_process(bench_instr_input)
    sim.add_sync_process(bench_free_rf_input)

    with sim.write_vcd("dump.vcd"):
        sim.run()
        print("Test OK")
    with open("result.v", "w") as f:
        f.write(verilog.convert(m, ports=[]))