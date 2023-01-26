from amaranth import *
from typing import Iterable
from coreblocks.params import GenParams
from coreblocks.params.fu_params import FuncBlockExtrasInputs, FuncUnitParams, FuncBlockParams
from coreblocks.params.layouts import FuncUnitLayouts, RSLayouts
from coreblocks.structs_common.rs import RS
from coreblocks.scheduler.wakeup_select import WakeupSelect
from coreblocks.transactions import Method
from coreblocks.utils.protocols import FuncUnit, FuncBlock
from coreblocks.transactions.lib import Collector

__all__ = ["RSFuncBlock", "RSBlock"]


class RSFuncBlock(Elaboratable):
    def __init__(self, gen_params: GenParams, func_units: Iterable[FuncUnit], rs_entries: int):
        self.gen_params = gen_params
        self.rs_layouts = gen_params.get(RSLayouts)
        self.fu_layouts = gen_params.get(FuncUnitLayouts)
        self.func_units = list(func_units)
        self.rs_entries = rs_entries
        self.optypes = set.union(*(func_unit.optypes for func_unit in func_units))

        self.insert = Method(i=self.rs_layouts.insert_in)
        self.select = Method(o=self.rs_layouts.select_out)
        self.update = Method(i=self.rs_layouts.update_in)
        self.get_result = Method(o=self.fu_layouts.accept)

    def elaborate(self, platform):
        m = Module()

        m.submodules.rs = rs = RS(
            gen_params=self.gen_params,
            rs_entries=self.rs_entries,
            ready_for=(func_unit.optypes for func_unit in self.func_units),
        )

        for n, func_unit in enumerate(self.func_units):
            wakeup_select = WakeupSelect(
                gen_params=self.gen_params, get_ready=rs.get_ready_list[n], take_row=rs.take, issue=func_unit.issue
            )
            setattr(m.submodules, f"func_unit_{n}", func_unit)
            setattr(m.submodules, f"wakeup_select_{n}", wakeup_select)

        m.submodules.collector = collector = Collector([func_unit.accept for func_unit in self.func_units])

        self.insert.proxy(m, rs.insert)
        self.select.proxy(m, rs.select)
        self.update.proxy(m, rs.update)
        self.get_result.proxy(m, collector.get_single)

        return m


class RSBlock(FuncBlockParams):
    def __init__(self, func_units: Iterable[FuncUnitParams], rs_entries: int):
        self.func_units = func_units
        self.rs_entries = rs_entries

    def get_module(self, gen_params: GenParams, inputs: FuncBlockExtrasInputs) -> FuncBlock:
        modules = list(u.get_module(gen_params, inputs) for u in self.func_units)
        rs_unit = RSFuncBlock(gen_params=gen_params, func_units=modules, rs_entries=self.rs_entries)
        return rs_unit
