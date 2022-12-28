from amaranth import *
from typing import Protocol
from coreblocks.params import GenParams
from coreblocks.params.isa import OpType
from coreblocks.structs_common.rs import RS
from coreblocks.scheduler.wakeup_select import WakeupSelect
from coreblocks.transactions import Method


class FuncUnit(Protocol):
    op_types: list[OpType]
    issue: Method
    accept: Method


class RSFuncBlock(Elaboratable):
    def __init__(self, gen_params: GenParams, func_unit: FuncUnit):
        self.gen_params = gen_params
        self.func_unit = func_unit
        self.op_types = func_unit.op_types

        self.insert = Method(i=self.rs_layouts.insert_in)
        self.select = Method(o=self.rs_layouts.select_out)
        self.update = Method(i=self.rs_layouts.update_in)
        self.get_result = Method(o=self.fu_layouts.accept)

    def elaborate(self):
        m = Module()

        m.submodules.rs = rs = RS(gen_params=self.gen_params)
        m.submodules.func_unit = self.func_unit
        m.submodules.wakeup_select = WakeupSelect(
            gen_params=self.gen_params, get_ready=rs.get_ready_list, take_row=rs.take, issue=self.func_unit.issue
        )

        return m
