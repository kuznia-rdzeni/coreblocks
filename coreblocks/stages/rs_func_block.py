from amaranth import *
from coreblocks.params import GenParams
from coreblocks.params.layouts import FuncUnitLayouts, RSLayouts
from coreblocks.structs_common.rs import RS
from coreblocks.scheduler.wakeup_select import WakeupSelect
from coreblocks.transactions import Method
from coreblocks.utils.protocols import FuncUnit

__all__ = ["RSFuncBlock"]


class RSFuncBlock(Elaboratable):
    def __init__(self, gen_params: GenParams, func_unit: FuncUnit):
        self.gen_params = gen_params
        self.rs_layouts = gen_params.get(RSLayouts)
        self.fu_layouts = gen_params.get(FuncUnitLayouts)
        self.func_unit = func_unit
        self.optypes = func_unit.optypes

        self.insert = Method(i=self.rs_layouts.insert_in)
        self.select = Method(o=self.rs_layouts.select_out)
        self.update = Method(i=self.rs_layouts.update_in)
        self.get_result = Method(o=self.fu_layouts.accept)

    def elaborate(self, platform):
        m = Module()

        m.submodules.rs = rs = RS(gen_params=self.gen_params)
        m.submodules.func_unit = self.func_unit
        m.submodules.wakeup_select = WakeupSelect(
            gen_params=self.gen_params, get_ready=rs.get_ready_list, take_row=rs.take, issue=self.func_unit.issue
        )

        self.insert.proxy(m, rs.insert)
        self.select.proxy(m, rs.select)
        self.update.proxy(m, rs.update)
        self.get_result.proxy(m, self.func_unit.accept)

        return m
