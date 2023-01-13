from amaranth import *
from typing import Iterable
from coreblocks.params import GenParams
from coreblocks.params.layouts import FuncUnitLayouts, RSLayouts
from coreblocks.structs_common.rs import RS
from coreblocks.scheduler.wakeup_select import WakeupSelect
from coreblocks.transactions import Method
from coreblocks.utils.protocols import FuncUnit
from coreblocks.transactions.lib import FIFO, ManyToOneConnectTrans

__all__ = ["RSFuncBlock"]


class RSFuncBlock(Elaboratable):
    def __init__(self, gen_params: GenParams, func_units: Iterable[FuncUnit]):
        self.gen_params = gen_params
        self.rs_layouts = gen_params.get(RSLayouts)
        self.fu_layouts = gen_params.get(FuncUnitLayouts)
        self.func_units = list(func_units)
        self.optypes = set.union(*(func_unit.optypes for func_unit in func_units))

        self.insert = Method(i=self.rs_layouts.insert_in)
        self.select = Method(o=self.rs_layouts.select_out)
        self.update = Method(i=self.rs_layouts.update_in)
        self.get_result = Method(o=self.fu_layouts.accept)

    def elaborate(self, platform):
        m = Module()

        # TODO: find a way to remove this FIFO. It increases FU latency without need.
        m.submodules.accept_fifo = accept_fifo = FIFO(self.fu_layouts.accept, 2)

        m.submodules.rs = rs = RS(
            gen_params=self.gen_params, ready_for=(func_unit.optypes for func_unit in self.func_units)
        )
        for n, func_unit in enumerate(self.func_units):
            wakeup_select = WakeupSelect(
                gen_params=self.gen_params, get_ready=rs.get_ready_list[n], take_row=rs.take, issue=func_unit.issue
            )
            setattr(m.submodules, f"func_unit_{n}", func_unit)
            setattr(m.submodules, f"wakeup_select_{n}", wakeup_select)

        m.submodules.connect = ManyToOneConnectTrans(
            get_results=[func_unit.accept for func_unit in self.func_units], put_result=accept_fifo.write
        )

        self.insert.proxy(m, rs.insert)
        self.select.proxy(m, rs.select)
        self.update.proxy(m, rs.update)
        self.get_result.proxy(m, accept_fifo.read)

        return m
