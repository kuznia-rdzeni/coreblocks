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

        self.free_rf_fifo = FIFO(self.gen_params.phys_regs_bits, 2**self.gen_params.phys_regs_bits)
        self.FRAT = FRAT(gen_params=self.gen_params)
        self.RRAT = RRAT(gen_params=self.gen_params)
        self.RF = RegisterFile(gen_params=self.gen_params)
        self.ROB = ReorderBuffer(gen_params=self.gen_params)
        self.RS = RS(gen_params=self.gen_params)

        self.reset = Method()

    def elaborate(self, platform):
        m = Module()

        @def_method(m, self.reset)
        def _(arg):
            # m.d.sync += ResetSignal().eq(1)
            pass

        m.submodules.free_rf_fifo = free_rf_fifo = self.free_rf_fifo
        m.submodules.FRAT = frat = self.FRAT
        m.submodules.RRAT = rrat = self.RRAT
        m.submodules.RF = rf = self.RF
        m.submodules.ROB = rob = self.ROB
        m.submodules.RS = rs = self.RS

        m.submodules.fifo_decode = fifo_decode = FIFO(self.gen_params.get(DecodeLayouts).decoded_instr, 2)
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
            rob_retire=rob.retire, r_rat_commit=rrat.commit, free_rf_put=free_rf_fifo.write, rf_free=rf.free
        )

        return m
