from typing import Iterable
from amaranth import *

from coreblocks.params.fu_params import ComponentDependencies, BlockComponentParams
from coreblocks.transactions.lib import FIFO, ConnectTrans, MethodProduct, Collector
from coreblocks.params.layouts import *
from coreblocks.params.genparams import GenParams
from coreblocks.frontend.decode import Decode
from coreblocks.structs_common.rat import FRAT, RRAT
from coreblocks.structs_common.rob import ReorderBuffer
from coreblocks.structs_common.rf import RegisterFile
from coreblocks.scheduler.scheduler import Scheduler
from coreblocks.stages.backend import ResultAnnouncement
from coreblocks.stages.retirement import Retirement
from coreblocks.peripherals.wishbone import WishboneMaster
from coreblocks.frontend.fetch import Fetch
from coreblocks.utils.fifo import BasicFifo
from coreblocks.utils.protocols import JumpUnit, LSUUnit, FuncUnitsHolder


__all__ = ["Core"]


class Core(Elaboratable):
    def __init__(self, *, gen_params: GenParams, wb_master: WishboneMaster):
        self.gen_params = gen_params
        self.wb_master = wb_master

        # make fifo_fetch visible outside the core for injecting instructions
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

        self.func_blocks_unifier = FuncBlocksUnifier(
            gen_params=gen_params,
            blocks=gen_params.func_units_config,
            dependencies=ComponentDependencies(wishbone_bus=wb_master),
        )

        self.announcement = ResultAnnouncement(
            gen=self.gen_params,
            get_result=self.func_blocks_unifier.get_result,
            rob_mark_done=self.ROB.mark_done,
            rs_write_val=self.func_blocks_unifier.update,
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
            reservation_stations=self.func_blocks_unifier.rs_blocks,
            gen_params=self.gen_params,
        )

        m.submodules.verify_branch = ConnectTrans(self.func_blocks_unifier.branch_result, self.fetch.verify_branch)

        m.submodules.announcement = self.announcement
        m.submodules.func_blocks_unifier = self.func_blocks_unifier
        m.submodules.retirement = Retirement(
            rob_retire=rob.retire, r_rat_commit=rrat.commit, free_rf_put=free_rf_fifo.write, rf_free=rf.free
        )

        return m


# TODO: Move somewhere else
class FuncBlocksUnifier(Elaboratable):
    def __init__(
        self, *, gen_params: GenParams, blocks: Iterable[BlockComponentParams], dependencies: ComponentDependencies
    ):
        self.rs_blocks = []

        for n, block in enumerate(blocks):
            self.rs_blocks.append(block.get_module(gen_params=gen_params, dependencies=dependencies))

        self.result_collector = Collector([block.get_result for block in self.rs_blocks])
        self.get_result = self.result_collector.get_single

        self.update_combiner = MethodProduct([block.update for block in self.rs_blocks])
        self.update = self.update_combiner.method

        branch_result_methods = [
            u.branch_result
            for b in self.rs_blocks
            if isinstance(b, FuncUnitsHolder)
            for u in b.func_units
            if isinstance(u, JumpUnit)
        ]

        self.branch_result_collector = None
        match branch_result_methods:
            case []:
                raise Exception("CPU without jumps")
            case [method]:
                self.branch_result = method
            case [*methods]:
                self.branch_result_collector = br_collector = Collector(methods)
                self.branch_result = br_collector.get_single

        commit_methods = [b.commit for b in self.rs_blocks if isinstance(b, LSUUnit)]

        self.commit_product = None
        match commit_methods:
            case []:
                self.commit = None
            case [method]:
                self.commit = method
            case [*methods]:
                self.commit_product = commit_product = MethodProduct(methods)
                self.commit = commit_product.method

    def elaborate(self, platform):
        m = Module()

        for n, unit in enumerate(self.rs_blocks):
            m.submodules[f"rs_block_{n}"] = unit

        m.submodules["result_collector"] = self.result_collector
        m.submodules["update_combiner"] = self.update_combiner

        if self.branch_result_collector is not None:
            m.submodules["branch_result_collector"] = self.branch_result_collector

        if self.commit_product is not None:
            m.submodules["commit_product"] = self.commit_product

        return m
