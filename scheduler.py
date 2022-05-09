import transactions as ts
from transactions import lib as tl
from amaranth import *
from amaranth.sim import *
from random import randint

from queue import Queue

in_data_layout = [
    ("src1", 5),
    ("src2", 5),
    ("dst", 5),
]

in_reg_layout = [
    ("phys_dst", 8),
]

combined_layout = [
    ("src1", 5),
    ("src2", 5),
    ("dst", 5),
    ("phys_dst", 8),
]

renamed_layout = [
    ("phys_src1", 8),
    ("phys_src2", 8),
    ("phys_dst", 8),
]

class GetFreeReg(Elaboratable):

    def __init__(self, fetch_instr:ts.Method, get_reg:ts.Method, pass_result:ts.Method) -> None:
        super().__init__()

        self.pass_result = pass_result
        self.fetch_instr = fetch_instr
        self.get_reg = get_reg
        self.enabled = Signal(1)

    def elaborate(self, platform):
        m = Module()

        with tl.Transaction().when_granted(m):
            instr = Record(in_data_layout)
            m.d.comb += instr.eq(self.fetch_instr(m))
            reg = Record(in_reg_layout)
            with m.If(instr.dst != 0):
                m.d.comb += reg.eq(self.get_reg(m))
            with m.Else():
                m.d.comb += reg.eq(0)
            
            result = Record(combined_layout)
            m.d.comb += result.src1.eq(instr.src1)
            m.d.comb += result.src2.eq(instr.src2)
            m.d.comb += result.dst.eq(instr.dst)
            m.d.comb += result.phys_dst.eq(reg.phys_dst)

            self.pass_result(m, result)

        return m

class RAT(Elaboratable):
    def __init__(self) -> None:
        super().__init__()

        self.query_rename = ts.Method(i=combined_layout)
        self.get_ready = ts.Method(o=renamed_layout)

    def elaborate(self, platform):
        m = Module()

        mem = Memory(width=8, depth=32)

        busy = Signal(1)
        get_now = Signal(1)
        queried = Signal(1)
        dst_pass = Signal(8)
        
        mem_read1 = mem.read_port(transparent=False)
        mem_read2 = mem.read_port(transparent=False)
        mem_write = mem.write_port()

        m.submodules += [mem_read1, mem_read2, mem_write]

        can_query = (busy == 0) #| (get_now == 1)

        m.d.comb += queried.eq(0)
        m.d.comb += get_now.eq(0)

        with self.query_rename.when_called(m, can_query) as arg:
            m.d.comb += mem_read1.addr.eq(arg.src1)
            m.d.comb += mem_read2.addr.eq(arg.src2)
            m.d.sync += dst_pass.eq(arg.phys_dst)

            with m.If(arg.dst != 0):
                m.d.comb += mem_write.data.eq(arg.phys_dst)
                m.d.comb += mem_write.addr.eq(arg.dst)
                m.d.comb += mem_write.en.eq(1)

            m.d.sync += busy.eq(1)
            m.d.comb += queried.eq(1)

        output = Record(renamed_layout)
        
        with self.get_ready.when_called(m, busy, output):
            m.d.comb += output.phys_src1.eq(mem_read1.data)
            m.d.comb += output.phys_src2.eq(mem_read2.data)
            m.d.comb += output.phys_dst.eq(dst_pass)

            m.d.comb += get_now.eq(1)
            m.d.sync += busy.eq(0)

        return m

def sig_len(layout):
    total_size = 0
    for _, width in layout:
        total_size += width
    return total_size

class Test(Elaboratable):

    def elaborate(self, platform):
        global reg_inp, instr_inp, out
        m = Module()
        tm = tl.TransactionModule(m)
        with tm.transactionContext():
            
            m.submodules.in_f1 = in_f1 = tl.FIFO(sig_len(in_data_layout), 3)
            m.submodules.in_f2 = in_f2 = tl.FIFO(sig_len(in_reg_layout), 128)
            m.submodules.rat = rat = RAT()
            m.submodules.getreg = GetFreeReg(in_f1.read, in_f2.read, rat.query_rename)
            m.submodules.instr_inp = instr_inp = tl.AdapterTrans(in_f1.write, i=in_data_layout)
            m.submodules.reg_inp = reg_inp = tl.AdapterTrans(in_f2.write, i=in_reg_layout)
            m.submodules.output = out = tl.AdapterTrans(rat.get_ready, o=renamed_layout)

        return tm

free_reg_queue = Queue()
inserted_reg_queue = Queue()

for i in range(1, 128):
    free_reg_queue.put(i)

input_queue = Queue()

rat_state = [0] * 32

def bench_reg_input():

    yield Passive()

    while True:
        if not free_reg_queue.empty():
            i = free_reg_queue.get()
            inserted_reg_queue.put(i)
            yield reg_inp.en.eq(1)
            yield reg_inp.data_in.eq(i)
            yield
            while (yield reg_inp.done) != 1:
                yield
        else:
            yield reg_inp.en.eq(0)
            yield
            # print("reg done")
        

def bench_input():
    for i in range(500):
        x, y, z = randint(0, 31), randint(0, 31), randint(0, 31)
        input_queue.put((x, y, z))
        rec = Record(in_data_layout)
        yield instr_inp.en.eq(0)
        yield rec.src1.eq(x)
        yield rec.src2.eq(y)
        yield rec.dst.eq(z)
        yield
        # print((yield rec.src1))
        yield instr_inp.en.eq(1)
        yield instr_inp.data_in.eq(rec)
        # print("ok", x, y, z)
        yield

        while (yield instr_inp.done) != 1:
            yield
        # print("executed")
        
    yield instr_inp.en.eq(0)
    yield
    yield
    yield
    yield
    print("done")
    return

def bench_output():
    yield Passive()
    while True:
        yield out.en.eq(1)
        yield
        while (yield out.done) != 1:
            yield

        x, y, z = input_queue.get()

        tgt_x = rat_state[x]
        tgt_y = rat_state[y]

        if z != 0:
            tgt_z = inserted_reg_queue.get()
            prev_val = rat_state[z]
            rat_state[z] = tgt_z
            if prev_val != 0:
                free_reg_queue.put(prev_val)
        else:
            tgt_z = 0
        
        remapped_x = (yield out.data_out.phys_src1)
        remapped_y = (yield out.data_out.phys_src2)
        remapped_z = (yield out.data_out.phys_dst)

        print(x, y, z, tgt_x, tgt_y, tgt_z, remapped_x, remapped_y, remapped_z)
        assert tgt_x == remapped_x
        assert tgt_y == remapped_y
        assert tgt_z == remapped_z
        yield out.en.eq(0)
        yield

if __name__ == "__main__":
    
    m = Test()
    sim = Simulator(m)
    sim.add_clock(1e-6)
    sim.add_sync_process(bench_input)
    sim.add_sync_process(bench_reg_input)
    sim.add_sync_process(bench_output)

    sim.run()

