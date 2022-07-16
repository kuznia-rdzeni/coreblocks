from amaranth import *
from coreblocks.transactions import Method, def_method
from coreblocks.transactions.lib import FIFO
from coreblocks.layouts import *
from coreblocks.genparams import GenParams
from coreblocks.decode import Decode
from coreblocks.rat import FRAT, RRAT
from coreblocks.reorder_buffer import ReorderBuffer
from coreblocks.rf import RegisterFile
from coreblocks.rs import RS
from coreblocks.scheduler import Scheduler
from coreblocks.wakeup_select import WakeupSelect
from coreblocks.functional_unit import AluFuncUnit
from coreblocks.backend import ResultAnnouncement
from coreblocks.retirement import Retirement

__all__ = ["Core"]


class Core(Elaboratable):
    def __init__(self, *, gen_params: GenParams, get_raw_instr: Method):
        self.gen_params = gen_params
        self.get_raw_instr = get_raw_instr
        self.put_reg = Method(i=[("reg", self.gen_params.phys_regs_bits)])

    def elaborate(self, platform):
        m = Module()

        m.submodules.free_rf_fifo = free_rf_fifo = FIFO(
            self.gen_params.phys_regs_bits, 2**self.gen_params.phys_regs_bits
        )

        @def_method(m, self.put_reg)
        def _(arg):
            free_rf_fifo.write(m, arg.reg)

        m.submodules.FRAT = frat = FRAT(gen_params=self.gen_params)
        m.submodules.RRAT = rrat = RRAT(gen_params=self.gen_params)
        m.submodules.RF = rf = RegisterFile(gen_params=self.gen_params)
        m.submodules.ROB = rob = ReorderBuffer(gen_params=self.gen_params)
        m.submodules.RS = rs = RS(gen_params=self.gen_params)

        self.RF = rf
        self.RRAT = rrat
        self.FRAT = frat

        m.submodules.fifo_decode = fifo_decode = FIFO(self.gen_params.get(DecodeLayouts).decoded_instr, 1)
        m.submodules.decode = Decode(
            gen_params=self.gen_params, get_raw=self.get_raw_instr, push_decoded=fifo_decode.write
        )

        m.submodules.scheduler = Scheduler(
            get_instr=fifo_decode.read,
            get_free_reg=free_rf_fifo.read,
            rat_rename=frat.rename,
            rob_put=rob.put,
            rf_read1=rf.read1,
            rf_read2=rf.read2,
            rs_alloc=rs.select,
            rs_insert=rs.insert,
            gen_params=self.gen_params,
        )

        m.submodules.alu = alu = AluFuncUnit(gen=self.gen_params)
        m.submodules.wakeup_select = WakeupSelect(
            gen_params=self.gen_params, get_ready=rs.get_ready_list, take_row=rs.take, issue=alu.issue
        )
        m.submodules.announcement = ResultAnnouncement(
            gen=self.gen_params,
            get_result=alu.accept,
            rob_mark_done=rob.mark_done,
            rs_write_val=rs.update,
            rf_write_val=rf.write,
        )
        m.submodules.retirement = Retirement(
            rob_retire=rob.retire, r_rat_commit=rrat.commit, free_rf_put=free_rf_fifo.write
        )

        return m
