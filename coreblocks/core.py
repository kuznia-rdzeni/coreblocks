from amaranth import *
from coreblocks.transactions import Method, def_method
from coreblocks.transactions.lib import FIFO
from coreblocks.params.isa import OpType
from coreblocks.params.layouts import *
from coreblocks.params.genparams import GenParams
from coreblocks.frontend.decode import Decode
from coreblocks.structs_common.rat import FRAT, RRAT
from coreblocks.structs_common.rob import ReorderBuffer
from coreblocks.structs_common.rf import RegisterFile
from coreblocks.structs_common.rs import RS
from coreblocks.scheduler.scheduler import Scheduler
from coreblocks.scheduler.wakeup_select import WakeupSelect
from coreblocks.fu.alu import AluFuncUnit
from coreblocks.stages.backend import ResultAnnouncement
from coreblocks.stages.retirement import Retirement
from coreblocks.peripherals.wishbone import WishboneMaster
from coreblocks.frontend.fetch import Fetch
from coreblocks.utils.fifo import BasicFifo

__all__ = ["Core"]


class Core(Elaboratable):
    def __init__(self, *, gen_params: GenParams, wb_master: WishboneMaster):
        self.gen_params = gen_params
        self.wb_master = wb_master

        # make fifo_fetch visible outside of the core for injecting instructions
        self.fifo_fetch = FIFO(self.gen_params.get(FetchLayouts).raw_instr, 2)
        self.free_rf_fifo = BasicFifo(
            self.gen_params.phys_regs_bits,
            2**self.gen_params.phys_regs_bits,
            init=[i for i in range(1, 2**self.gen_params.phys_regs_bits)],
        )
        self.fetch = Fetch(self.gen_params, self.wb_master, self.fifo_fetch.write)
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
            m.d.comb += ResetSignal().eq(1)

        m.submodules.free_rf_fifo = free_rf_fifo = self.free_rf_fifo
        m.submodules.FRAT = frat = self.FRAT
        m.submodules.RRAT = rrat = self.RRAT
        m.submodules.RF = rf = self.RF
        m.submodules.ROB = rob = self.ROB
        m.submodules.RS = rs = self.RS

        m.submodules.fifo_fetch = self.fifo_fetch
        m.submodules.fetch = self.fetch

        m.submodules.fifo_decode = fifo_decode = FIFO(self.gen_params.get(DecodeLayouts).decoded_instr, 2)
        m.submodules.decode = Decode(
            gen_params=self.gen_params, get_raw=self.fifo_fetch.read, push_decoded=fifo_decode.write
        )

        m.submodules.scheduler = Scheduler(
            get_instr=fifo_decode.read,
            get_free_reg=free_rf_fifo.read,
            rat_rename=frat.rename,
            rob_put=rob.put,
            rf_read1=rf.read1,
            rf_read2=rf.read2,
            rs_alloc=[(rs.select, [OpType.ARITHMETIC, OpType.COMPARE, OpType.LOGIC, OpType.SHIFT])],
            rs_insert=[rs.insert],
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
