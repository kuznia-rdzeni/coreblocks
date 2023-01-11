from amaranth import Elaboratable, Module
from coreblocks.transactions.lib import FIFO
from coreblocks.params.layouts import *
from coreblocks.params.genparams import GenParams
from coreblocks.frontend.decode import Decode
from coreblocks.structs_common.rat import FRAT, RRAT
from coreblocks.structs_common.rob import ReorderBuffer
from coreblocks.structs_common.rf import RegisterFile
from coreblocks.scheduler.scheduler import Scheduler
from coreblocks.fu.alu import AluFuncUnit
from coreblocks.stages.backend import ResultAnnouncement
from coreblocks.stages.retirement import Retirement
from coreblocks.stages.rs_func_block import RSFuncBlock
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

        alu = AluFuncUnit(gen=self.gen_params)
        self.alu_block = RSFuncBlock(gen_params=self.gen_params, func_unit=alu)
        self.announcement = ResultAnnouncement(
            gen=self.gen_params,
            get_result=self.alu_block.get_result,
            rob_mark_done=self.ROB.mark_done,
            rs_write_val=self.alu_block.update,
            rf_write_val=self.RF.write,
        )

    def elaborate(self, platform):
        m = Module()

        m.submodules.free_rf_fifo = free_rf_fifo = self.free_rf_fifo
        m.submodules.FRAT = frat = self.FRAT
        m.submodules.RRAT = rrat = self.RRAT
        m.submodules.RF = rf = self.RF
        m.submodules.ROB = rob = self.ROB

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
            rs_alloc=self.alu_block.select,
            rs_insert=self.alu_block.insert,
            gen_params=self.gen_params,
        )

        m.submodules.alu_block = self.alu_block
        m.submodules.announcement = self.announcement
        m.submodules.retirement = Retirement(
            rob_retire=rob.retire, r_rat_commit=rrat.commit, free_rf_put=free_rf_fifo.write, rf_free=rf.free
        )

        return m
