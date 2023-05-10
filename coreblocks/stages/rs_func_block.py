from collections.abc import Collection
from amaranth import *
from dataclasses import dataclass
from coreblocks.params import *
from coreblocks.structs_common.rs import RS
from coreblocks.scheduler.wakeup_select import WakeupSelect
from coreblocks.transactions import Method
from coreblocks.utils.debug_signals import auto_debug_signals, SignalBundle
from coreblocks.utils.protocols import FuncUnit, FuncBlock
from coreblocks.transactions.lib import Collector

__all__ = ["RSFuncBlock", "RSBlockComponent"]


class RSFuncBlock(FuncBlock, Elaboratable):
    """
    Module combining multiple functional units with single RS unit. With
    input interface of RS and output interface of single FU.

    Attributes
    ----------
    insert: Method
        RS insert method.
    select: Method
        RS select method.
    update: Method
        RS update method.
    get_result: Method
        Method used for getting single result out of one of the FUs. It uses
        layout described by `FuncUnitLayouts`.
    """

    def __init__(self, gen_params: GenParams, func_units: Iterable[tuple[FuncUnit, set[OpType]]], rs_entries: int):
        """
        Parameters
        ----------
        gen_params: GenParams
            Core generation parameters.
        func_units: Iterable[FuncUnit]
            Functional units to be used by this module.
        rs_entries: int
            Number of entries in RS.
        """
        self.gen_params = gen_params
        self.rs_layouts = gen_params.get(RSLayouts)
        self.fu_layouts = gen_params.get(FuncUnitLayouts)
        self.func_units = list(func_units)
        self.rs_entries = rs_entries

        self.insert = Method(i=self.rs_layouts.insert_in)
        self.select = Method(o=self.rs_layouts.select_out)
        self.update = Method(i=self.rs_layouts.update_in)
        self.get_result = Method(o=self.fu_layouts.accept)

    def elaborate(self, platform):
        m = Module()

        m.submodules.rs = self.rs = RS(
            gen_params=self.gen_params,
            rs_entries=self.rs_entries,
            ready_for=(optypes for _, optypes in self.func_units),
        )

        for n, (func_unit, _) in enumerate(self.func_units):
            wakeup_select = WakeupSelect(
                gen_params=self.gen_params,
                get_ready=self.rs.get_ready_list[n],
                take_row=self.rs.take,
                issue=func_unit.issue,
            )
            m.submodules[f"func_unit_{n}"] = func_unit
            m.submodules[f"wakeup_select_{n}"] = wakeup_select

        m.submodules.collector = collector = Collector([func_unit.accept for func_unit, _ in self.func_units])

        self.insert.proxy(m, self.rs.insert)
        self.select.proxy(m, self.rs.select)
        self.update.proxy(m, self.rs.update)
        self.get_result.proxy(m, collector.method)

        return m

    def debug_signals(self) -> SignalBundle:
        # TODO: enhanced auto_debug_signals would allow to remove this method
        return {
            "insert": self.insert.debug_signals(),
            "select": self.select.debug_signals(),
            "update": self.update.debug_signals(),
            "get_result": self.get_result.debug_signals(),
            "rs": self.rs,
            "func_units": {i: auto_debug_signals(b) for i, b in enumerate(self.func_units)},
        }


@dataclass(frozen=True)
class RSBlockComponent(BlockComponentParams):
    func_units: Collection[FunctionalComponentParams]
    rs_entries: int

    def get_module(self, gen_params: GenParams) -> FuncBlock:
        modules = list((u.get_module(gen_params), u.get_optypes()) for u in self.func_units)
        rs_unit = RSFuncBlock(gen_params=gen_params, func_units=modules, rs_entries=self.rs_entries)
        return rs_unit

    def get_optypes(self) -> set[OpType]:
        return optypes_supported(self.func_units)
