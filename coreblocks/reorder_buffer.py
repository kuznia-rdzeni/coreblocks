from . import transactions as ts
from .transactions import lib as tl
from amaranth import *

log_rob_len = 7
log_reg_cnt = 5
log_phys_reg_cnt = 8

in_layout = [
    ("dst_reg", log_reg_cnt),
    ("phys_dst_reg", log_phys_reg_cnt),
]

id_layout = [
    ("rob_id", log_rob_len),
]

out_layout = [
    ("dst_reg", log_reg_cnt),
    ("phys_dst_reg", log_phys_reg_cnt),
]

internal_layout = [
    ("dst_reg", log_reg_cnt),
    ("phys_dst_reg", log_phys_reg_cnt),
    ("done", 1),
]


class ReorderBuffer(Elaboratable):
    def __init__(self) -> None:
        super().__init__()

        self.put = ts.Method(i=in_layout, o=id_layout)
        self.mark_done = ts.Method(i=id_layout)
        self.retire = ts.Method(o=out_layout)
        self.data = Array(Record(internal_layout) for _ in range(2**log_rob_len))

        self.start_cnt = Signal(log_rob_len)
        self.end_cnt = Signal(log_rob_len)

    def elaborate(self, platform) -> Module:
        m = Module()

        put_possible = self.end_cnt != self.start_cnt - 1

        output = Record(out_layout)

        with self.retire.body(m, ready=self.data[self.start_cnt].done, out=output):
            m.d.comb += output.eq(self.data[self.start_cnt])
            m.d.sync += self.start_cnt.eq(self.start_cnt + 1)
            m.d.sync += self.data[self.start_cnt].done.eq(0)

        put_output = Record(id_layout)

        with self.put.body(m, ready=put_possible, out=put_output) as arg:
            m.d.sync += self.data[self.end_cnt].dst_reg.eq(arg.dst_reg)
            m.d.sync += self.data[self.end_cnt].phys_dst_reg.eq(arg.phys_dst_reg)
            m.d.sync += self.data[self.end_cnt].done.eq(0)
            m.d.sync += self.end_cnt.eq(self.end_cnt + 1)
            m.d.comb += put_output.rob_id.eq(self.end_cnt)

        # TODO: There is a potential race condition when ROB is flushed.
        # If functional units aren't flushed, finished obsolete instructions
        # could mark fields in ROB as done when they shouldn't.
        with self.mark_done.body(m) as arg:
            m.d.sync += self.data[arg.rob_id].done.eq(1)

        return m
