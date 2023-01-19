from amaranth import *
from typing import Iterable
from coreblocks.params import GenParams
from coreblocks.params.layouts import FuncUnitLayouts, RSLayouts
from coreblocks.structs_common.rs import RS
from coreblocks.scheduler.wakeup_select import WakeupSelect
from coreblocks.transactions import Method
from coreblocks.utils.protocols import FuncUnit
from coreblocks.transactions.lib import Collector

__all__ = ["RSFuncBlock"]


class RSFuncBlock(Elaboratable):
    """
    Module combining multiple functional units with single RS unit. With
    input interface of RS and output interface of single FU.

    Attributes
    ----------
    optypes: set[OpType]
        Set of `OpType`\\s supported by this unit.
    insert: Method
        RS insert method.
    select: Method
        RS select method.
    update: Method
        RS update method.
    get_result: Method
        Method used for getting single result out of one of FUs. It uses
        layout described by `FuncUnitLayouts`.
    """
    def __init__(self, gen_params: GenParams, func_units: Iterable[FuncUnit]):
        """
        Parameters
        ----------
        gen_params: GenParams
            Core generation parameters.
        func_units: Iterable[FuncUnit]
            Functional units to be used by this module.
        """
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

        m.submodules.rs = rs = RS(
            gen_params=self.gen_params, ready_for=(func_unit.optypes for func_unit in self.func_units)
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
